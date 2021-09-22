from enum import IntEnum, unique

from nmigen import Signal, Elaboratable, Module, ResetInserter, Cat
from nmigen_soc.wishbone import Interface as WishboneInterface
from nmigen.lib.fifo import SyncFIFOBuffered

from nmigen.back import verilog


@unique
class RegEnum(IntEnum):
    BT_CTRL = 0
    BMC2HOST_HOST2BMC = 1
    BT_INTMASK = 2


@unique
class BMCRegEnum(IntEnum):
    IRQ_MASK = 0
    IRQ_STATUS = 1
    BT_CTRL = 4
    BMC2HOST_HOST2BMC = 5


@unique
class StateEnum(IntEnum):
    IDLE = 0
    ACK = 1


@unique
class BMCIRQEnum(IntEnum):
    TARGET_TO_BMC_ATTN = 0
    TARGET_NOT_BUSY = 1


class IPMI_BT(Elaboratable):
    def __init__(self, depth=64):
        self.depth = depth

        self.bmc_wb = WishboneInterface(data_width=8, addr_width=3)
        self.bmc_irq = Signal()

        self.target_wb = WishboneInterface(data_width=8, addr_width=2)
        self.target_irq = Signal()

    def elaborate(self, platform):
        m = Module()

        # Reset signals for the FIFOs, since BT_CTRL needs to be able to clear them
        reset_from_bmc_fifo = Signal()
        reset_from_target_fifo = Signal()
        m.d.sync += [
            reset_from_bmc_fifo.eq(0),
            reset_from_target_fifo.eq(0)
        ]

        # BMC -> Target FIFO
        m.submodules.from_bmc_fifo = from_bmc_fifo = ResetInserter(
            reset_from_bmc_fifo)(SyncFIFOBuffered(width=8, depth=self.depth))

        # Target -> BMC FIFO
        m.submodules.from_target_fifo = from_target_fifo = ResetInserter(
            reset_from_target_fifo)(SyncFIFOBuffered(width=8, depth=self.depth))

        # Wire up wishbone to FIFO write
        m.d.comb += [
            from_bmc_fifo.w_data.eq(self.bmc_wb.dat_w),
            from_target_fifo.w_data.eq(self.target_wb.dat_w)
        ]

        # Some wishbone helpers
        is_bmc_write = Signal()
        is_bmc_read = Signal()
        m.d.comb += [
            is_bmc_write.eq(self.bmc_wb.stb & self.bmc_wb.cyc & self.bmc_wb.we),
            is_bmc_read.eq(self.bmc_wb.stb & self.bmc_wb.cyc & ~self.bmc_wb.we)
        ]
        is_target_read = Signal()
        is_target_write = Signal()
        m.d.comb += [
            is_target_write.eq(self.target_wb.stb & self.target_wb.cyc & self.target_wb.we),
            is_target_read.eq(self.target_wb.stb & self.target_wb.cyc & ~self.target_wb.we)
        ]

        # BMC and target wishbone state machine
        bmc_state = Signal(StateEnum, reset=StateEnum.IDLE)
        target_state = Signal(StateEnum, reset=StateEnum.IDLE)

        m.d.sync += [
            from_bmc_fifo.w_en.eq(0),
            from_bmc_fifo.r_en.eq(0),
            from_target_fifo.w_en.eq(0),
            from_target_fifo.r_en.eq(0)
        ]

        m.d.sync += [
            self.bmc_wb.ack.eq(0),
            self.target_wb.ack.eq(0)
        ]

        # Don't read from empty FIFOs
        from_bmc_fifo_read_data = Signal(8)
        m.d.comb += from_bmc_fifo_read_data.eq(0)
        with m.If(from_bmc_fifo.r_rdy):
            m.d.comb += from_bmc_fifo_read_data.eq(from_bmc_fifo.r_data)

        from_target_fifo_read_data = Signal(8)
        m.d.comb += from_target_fifo_read_data.eq(0)
        with m.If(from_target_fifo.r_rdy):
            m.d.comb += from_target_fifo_read_data.eq(from_target_fifo.r_data)

        # BT_CTRL bits
        target_to_bmc_attn = Signal()
        bmc_to_target_attn = Signal()
        sms_attn = Signal()
        platform_reserved = Signal()
        bmc_busy = Signal()
        target_busy = Signal()

        bt_ctrl = Signal(8)
        m.d.comb += bt_ctrl.eq(Cat(0, 0, target_to_bmc_attn, bmc_to_target_attn,
                                   sms_attn, platform_reserved, target_busy,
                                   bmc_busy))

        # BT_INTMASK (target interrupt mask) bits
        bmc_to_target_irq_en = Signal()
        bmc_to_target_irq = Signal()

        m.d.comb += self.target_irq.eq(bmc_to_target_irq_en & bmc_to_target_irq)

        # BMC interrupt bits. These are not architected by the IPMI BT spec. The
        # Linux driver expects to get an interrupt whenever target_to_bmc_attn
        # goes high (ready to read) or target_busy goes low (ready to write). We
        # don't interrupt on bmc_to_target_attn going low (which is also required
        # for ready to write) but rely on the target driver setting target_busy low
        # right after it sets bmc_to_target_attn low.
        bmc_irq_en = Signal(2)
        bmc_irq = Signal(2)

        m.d.comb += self.bmc_irq.eq(bmc_irq_en & bmc_irq)

        # Target wishbone state machine
        with m.Switch(target_state):
            with m.Case(StateEnum.IDLE):
                with m.If(is_target_write):
                    with m.Switch(self.target_wb.adr):
                        with m.Case(RegEnum.BT_CTRL):
                            # Bit 0, write 1 to clear the write fifo (ie from_target_fifo)
                            with m.If(self.target_wb.dat_w[0]):
                                m.d.sync += reset_from_target_fifo.eq(1)

                            # Bit 1 is meant to set the read FIFO to the next valid
                            # position, but since we only have a single buffer this
                            # doesn't need to do anything.

                            with m.If(self.target_wb.dat_w[2]):
                                # Trigger an interrupt whenever we set target_to_bmc_attn
                                with m.If(bmc_irq_en[BMCIRQEnum.TARGET_TO_BMC_ATTN]):
                                    m.d.sync += bmc_irq[BMCIRQEnum.TARGET_TO_BMC_ATTN].eq(1)
                                m.d.sync += target_to_bmc_attn.eq(1)

                            # Bit 3, write 1 to clear bmc_to_target_attn
                            with m.If(self.target_wb.dat_w[3]):
                                m.d.sync += bmc_to_target_attn.eq(0)

                            # Bit 4, write 1 to clear sms_attn
                            with m.If(self.target_wb.dat_w[4]):
                                m.d.sync += sms_attn.eq(0)

                            # Bit 5, write 1 to set platform reserved
                            with m.If(self.target_wb.dat_w[5]):
                                m.d.sync += platform_reserved.eq(1)

                            # Bit 6, write 1 to toggle target_busy
                            with m.If(self.target_wb.dat_w[6]):
                                # Trigger an interrupt whenever we clear target_busy
                                with m.If(target_busy & bmc_irq_en[BMCIRQEnum.TARGET_NOT_BUSY]):
                                    m.d.sync += bmc_irq[BMCIRQEnum.TARGET_NOT_BUSY].eq(1)
                                m.d.sync += target_busy.eq(~target_busy)

                            # Bit 7, read only

                        with m.Case(RegEnum.BMC2HOST_HOST2BMC):
                            # Only assert write if there is space
                            m.d.sync += from_target_fifo.w_en.eq(from_target_fifo.w_rdy)

                        with m.Case(RegEnum.BT_INTMASK):
                            # Bit 0, 0/1 write
                            m.d.sync += bmc_to_target_irq_en.eq(self.target_wb.dat_w[0])

                            # Bit 1, write 1 to clear interrupt
                            with m.If(self.target_wb.dat_w[1]):
                                m.d.sync += bmc_to_target_irq.eq(0)

                    m.d.sync += [
                        self.target_wb.ack.eq(1),
                        target_state.eq(StateEnum.ACK)
                    ]

                with m.If(is_target_read):
                    with m.Switch(self.target_wb.adr):
                        with m.Case(RegEnum.BT_CTRL):
                            m.d.sync += self.target_wb.dat_r.eq(bt_ctrl)

                        with m.Case(RegEnum.BMC2HOST_HOST2BMC):
                            m.d.sync += [
                                self.target_wb.dat_r.eq(from_bmc_fifo_read_data),
                                from_bmc_fifo.r_en.eq(from_bmc_fifo.r_rdy),
                            ]

                        with m.Case(RegEnum.BT_INTMASK):
                            m.d.sync += self.target_wb.dat_r.eq(Cat(bmc_to_target_irq_en, bmc_to_target_irq))

                    m.d.sync += [
                        self.target_wb.ack.eq(1),
                        target_state.eq(StateEnum.ACK)
                    ]

            with m.Case(StateEnum.ACK):
                m.d.sync += [
                    self.target_wb.ack.eq(0),
                    target_state.eq(StateEnum.IDLE),
                ]

        # BMC wishbone state machine
        with m.Switch(bmc_state):
            with m.Case(StateEnum.IDLE):
                with m.If(is_bmc_write):
                    with m.Switch(self.bmc_wb.adr):
                        with m.Case(BMCRegEnum.BT_CTRL):
                            # Bit 0, write 1 to clear the write fifo (ie from_bmc_fifo)
                            with m.If(self.bmc_wb.dat_w[0]):
                                m.d.sync += reset_from_bmc_fifo.eq(1)

                            # Bit 1 is meant to set the read FIFO to the next valid
                            # position, but since we only have a single buffer this
                            # doesn't need to do anything.

                            # Bit 2, write to clear target_to_bmc_attn
                            with m.If(self.bmc_wb.dat_w[2]):
                                m.d.sync += target_to_bmc_attn.eq(0)

                            # Bit 3, write 1 to set bmc_to_target_attn
                            with m.If(self.bmc_wb.dat_w[3]):
                                # Trigger an interrupt whenever we set bmc_to_target_attn
                                with m.If(bmc_to_target_irq_en):
                                    m.d.sync += bmc_to_target_irq.eq(1)
                                m.d.sync += bmc_to_target_attn.eq(1)

                            # Bit 4, write 1 to set sms_attn
                            with m.If(self.bmc_wb.dat_w[4]):
                                # Trigger an interrupt whenever we set sms_attn
                                with m.If(bmc_to_target_irq_en):
                                    m.d.sync += bmc_to_target_irq.eq(1)
                                m.d.sync += sms_attn.eq(1)

                            # Bit 5, write 1 to clear platform reserved
                            with m.If(self.bmc_wb.dat_w[5]):
                                m.d.sync += platform_reserved.eq(0)

                            # Bit 6, read only

                            # Bit 7, write 1 to toggle bmc_busy
                            with m.If(self.bmc_wb.dat_w[7]):
                                m.d.sync += bmc_busy.eq(~bmc_busy)

                        with m.Case(BMCRegEnum.BMC2HOST_HOST2BMC):
                            # Only assert write if there is space
                            m.d.sync += from_bmc_fifo.w_en.eq(from_bmc_fifo.w_rdy)

                        with m.Case(BMCRegEnum.IRQ_MASK):
                            m.d.sync += bmc_irq_en.eq(self.bmc_wb.dat_w)

                        with m.Case(BMCRegEnum.IRQ_STATUS):
                            m.d.sync += bmc_irq.eq(self.bmc_wb.dat_w)

                    m.d.sync += [
                        self.bmc_wb.ack.eq(1),
                        bmc_state.eq(StateEnum.ACK)
                    ]

                with m.If(is_bmc_read):
                    with m.Switch(self.bmc_wb.adr):
                        with m.Case(BMCRegEnum.BT_CTRL):
                            m.d.sync += self.bmc_wb.dat_r.eq(bt_ctrl)

                        with m.Case(BMCRegEnum.BMC2HOST_HOST2BMC):
                            m.d.sync += [
                                self.bmc_wb.dat_r.eq(from_target_fifo_read_data),
                                from_target_fifo.r_en.eq(from_target_fifo.r_rdy),
                            ]

                        with m.Case(BMCRegEnum.IRQ_MASK):
                            m.d.sync += self.bmc_wb.dat_r.eq(bmc_irq_en)

                        with m.Case(BMCRegEnum.IRQ_STATUS):
                            m.d.sync += self.bmc_wb.dat_r.eq(bmc_irq)

                    m.d.sync += [
                        self.bmc_wb.ack.eq(1),
                        bmc_state.eq(StateEnum.ACK)
                    ]

            with m.Case(StateEnum.ACK):
                m.d.sync += [
                    self.bmc_wb.ack.eq(0),
                    bmc_state.eq(StateEnum.IDLE),
                ]

        return m


if __name__ == "__main__":
    top = IPMI_BT()
    with open("ipmi_bt.v", "w") as f:
        f.write(verilog.convert(top))
