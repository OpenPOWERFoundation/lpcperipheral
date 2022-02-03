from enum import Enum, unique

from amaranth import Signal, Elaboratable, Module
from amaranth_soc.wishbone import Interface as WishboneInterface
from amaranth.back import verilog


@unique
class RegEnum(Enum):
    RXTX_DLL = 0
    IER_DLM = 1
    IIR_FCR = 2
    LCR = 3
    MCR = 4
    LSR = 5
    MSR = 6
    SCR = 7


IER_ERBFI = 0
IER_ETBEI = 1

LCR_DLAB = 7


class VUart(Elaboratable):
    """
    Virtual UART. Presents a 16550 style interface over a wishbone slave
    and connects that to a read and write FIFO.

    Parameters
    ----------

    Attributes
    ----------
    """
    def __init__(self):
        # Write port of FIFO A
        self.w_data = Signal(8)
        self.w_rdy = Signal()
        self.w_en = Signal()

        # Read port of FIFO B
        self.r_data = Signal(8)
        self.r_rdy = Signal()
        self.r_en = Signal()

        self.irq = Signal()

        # Wishbone slave
        self.wb = WishboneInterface(data_width=8, addr_width=3)

    def elaborate(self, platform):
        m = Module()

        # 16550 registers
        ier = Signal(4)  # Interrupt enable register
        #    ERBFI: enable RX interrupt
        #    ETBEI: enable TX interrupt
        iir = Signal(4, reset=0b1)  # Interrupt identification register
        #   Interrupt pending
        #   Interrupt ID
        fcr = Signal(8)  # FIFO control register, ignore
        lcr = Signal(8)  # Line control register, ignore all but DLAB bit
        mcr = Signal(5)  # Modem control register, ignore
        lsr = Signal(8)  # Line status register
        #    DR: 1 when something in the fifo, reset to 0 when fifo empty
        #    OE: RX fifo full and new character was attempted to add, need signal
        #    from remote, not fifo full condition
        #    THRE: always 1
        #    TEMPT: always 1
        msr = Signal(8)  # Modem status register, ignore
        scr = Signal(8)  # Scratch register, ignore
        dll = Signal(8)  # Divisor latch LS, ignore
        dlm = Signal(8)  # Divisor latch MS, ignore

        # Some helpers
        is_write = Signal()
        is_read = Signal()
        m.d.comb += [
            is_write.eq(self.wb.stb & self.wb.cyc & self.wb.we),
            is_read.eq(self.wb.stb & self.wb.cyc & ~self.wb.we),
        ]

        dlab = Signal()
        m.d.comb += dlab.eq(lcr[LCR_DLAB])

        # Don't read from an empty FIFO
        read_data = Signal(8)
        m.d.comb += read_data.eq(0)
        with m.If(self.r_rdy):
            m.d.comb += read_data.eq(self.r_data)

        m.d.sync += self.r_en.eq(0)
        m.d.sync += self.w_en.eq(0)

        # IRQ handling.
        #
        # On RX we raise an interrupt if there is anything in the RX FIFO. We
        # could optimise this by checking for a certain FIFO depth as well as
        # a timeout, similar to real 16550 hardware.
        #
        # For TX we can't assume the other end is consuming entries from the FIFO,
        # so we can't hook the interrupt, THRE and TEMPT bits to it. For now we
        # just always claim the TX FIFO is empty.
        m.d.comb += self.irq.eq(0)
        m.d.comb += iir.eq(0b0001)       # IIR bit 0 is high for no IRQ

        # Lower priority is the TX interrupt. In this case we always raise an
        # interrupt if the enable bit is set
        with m.If(ier[IER_ETBEI]):
            m.d.comb += [
                self.irq.eq(1),
                iir.eq(0b0010),
            ]

        # Highest priority is the RX interrupt. This overrides the TX interrupt
        # above.
        with m.If(ier[IER_ERBFI]):
            # Are there any entries in the RX FIFO?
            with m.If(self.r_rdy):
                m.d.comb += [
                    self.irq.eq(1),
                    iir.eq(0b0100),
                ]

        with m.FSM():
            with m.State('IDLE'):
                # Write
                with m.If(is_write):
                    with m.Switch(self.wb.adr):
                        with m.Case(RegEnum.RXTX_DLL):
                            with m.If(dlab):
                                m.d.sync += dll.eq(self.wb.dat_w)
                            with m.Else():
                                m.d.sync += self.w_data.eq(self.wb.dat_w)
                                with m.If(self.w_rdy):
                                    m.d.sync += self.w_en.eq(1)

                        with m.Case(RegEnum.IER_DLM):
                            with m.If(dlab):
                                m.d.sync += dlm.eq(self.wb.dat_w)
                            with m.Else():
                                m.d.sync += ier.eq(self.wb.dat_w)

                        with m.Case(RegEnum.IIR_FCR):
                            m.d.sync += fcr.eq(self.wb.dat_w)

                        with m.Case(RegEnum.LCR):
                            m.d.sync += lcr.eq(self.wb.dat_w)

                        with m.Case(RegEnum.MCR):
                            m.d.sync += mcr.eq(self.wb.dat_w)

                        with m.Case(RegEnum.MSR):
                            m.d.sync += msr.eq(self.wb.dat_w)

                        with m.Case(RegEnum.SCR):
                            m.d.sync += scr.eq(self.wb.dat_w)

                    m.d.sync += self.wb.ack.eq(1)
                    m.next = 'ACK'

                # Read
                with m.Elif(is_read):
                    with m.Switch(self.wb.adr):
                        with m.Case(RegEnum.RXTX_DLL):
                            with m.If(dlab):
                                m.d.sync += self.wb.dat_r.eq(dll)
                            with m.Else():
                                m.d.sync += self.wb.dat_r.eq(read_data)
                                with m.If(self.r_rdy):
                                    m.d.sync += self.r_en.eq(1)

                        with m.Case(RegEnum.IER_DLM):
                            with m.If(dlab):
                                m.d.sync += self.wb.dat_r.eq(dlm)
                            with m.Else():
                                m.d.sync += self.wb.dat_r.eq(ier)

                        with m.Case(RegEnum.IIR_FCR):
                            m.d.sync += self.wb.dat_r.eq(iir)

                        with m.Case(RegEnum.LCR):
                            m.d.sync += self.wb.dat_r.eq(lcr)

                        with m.Case(RegEnum.MCR):
                            m.d.sync += self.wb.dat_r.eq(mcr)

                        with m.Case(RegEnum.LSR):
                            m.d.sync += [
                                self.wb.dat_r.eq(0),
                                self.wb.dat_r[0].eq(self.r_rdy),
                                # Should we do something with the OE bit?
                                self.wb.dat_r[1].eq(0),
                                # Set THRE always to 1
                                self.wb.dat_r[5].eq(1),
                                # Set TEMT always to 1
                                self.wb.dat_r[6].eq(1)
                            ]

                        with m.Case(RegEnum.MSR):
                            m.d.sync += self.wb.dat_r.eq(msr)

                        with m.Case(RegEnum.SCR):
                            m.d.sync += self.wb.dat_r.eq(scr)

                    m.d.sync += self.wb.ack.eq(1)
                    m.next = 'ACK'

            with m.State('ACK'):
                m.d.sync += self.wb.ack.eq(0)
                m.next = 'IDLE'

        return m


if __name__ == "__main__":
    top = VUart()
    with open("vuart.v", "w") as f:
        f.write(verilog.convert(top))
