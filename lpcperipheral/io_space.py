from amaranth import Elaboratable, Module, Signal
from amaranth.back import verilog
from amaranth_soc.wishbone import Decoder as WishboneDecoder
from amaranth_soc.wishbone import Interface as WishboneInterface
from amaranth_soc.memory import MemoryMap

from .ipmi_bt import IPMI_BT
from .vuart_joined import VUartJoined


class IOSpace(Elaboratable):
    def __init__(self, vuart_depth=2048, bmc_vuart_addr=0x0, bmc_ipmi_addr=0x1000,
                 bmc_lpc_ctrl_addr=0x2000,
                 target_vuart_addr=0x3f8, target_ipmi_addr=0xe4):
        self.vuart_depth = vuart_depth
        self.bmc_vuart_addr = bmc_vuart_addr
        self.bmc_ipmi_addr = bmc_ipmi_addr
        self.bmc_lpc_ctrl_addr = bmc_lpc_ctrl_addr
        self.target_vuart_addr = target_vuart_addr
        self.target_ipmi_addr = target_ipmi_addr

        self.bmc_vuart_irq = Signal()
        self.bmc_ipmi_irq = Signal()
        self.bmc_wb = WishboneInterface(addr_width=14, data_width=32, granularity=8)

        self.lpc_ctrl_wb = WishboneInterface(addr_width=3, data_width=32, granularity=8)

        self.target_vuart_irq = Signal()
        self.target_ipmi_irq = Signal()
        self.target_wb = WishboneInterface(addr_width=16, data_width=8, features=["err"])

        self.error_wb = WishboneInterface(addr_width=2, data_width=8,
                                          features=["err"])

    def elaborate(self, platform):
        m = Module()

        m.submodules.vuart_joined = vuart_joined = VUartJoined(depth=self.vuart_depth)
        m.submodules.ipmi_bt = ipmi_bt = IPMI_BT()

        # BMC address decode
        m.submodules.bmc_decode = bmc_decode = WishboneDecoder(addr_width=14, data_width=32, granularity=8)

        bmc_ipmi_bus = ipmi_bt.bmc_wb
        bmc_ipmi_bus.memory_map = MemoryMap(addr_width=5, data_width=8)
        bmc_decode.add(bmc_ipmi_bus, addr=self.bmc_ipmi_addr)

        bmc_vuart_bus = vuart_joined.wb_a
        bmc_vuart_bus.memory_map = MemoryMap(addr_width=5, data_width=8)
        bmc_decode.add(bmc_vuart_bus, addr=self.bmc_vuart_addr)

        lpc_ctrl_bus = self.lpc_ctrl_wb
        lpc_ctrl_bus.memory_map = MemoryMap(addr_width=5, data_width=8)
        bmc_decode.add(lpc_ctrl_bus, addr=self.bmc_lpc_ctrl_addr)

        m.d.comb += [
            self.bmc_ipmi_irq.eq(ipmi_bt.bmc_irq),
            self.bmc_vuart_irq.eq(vuart_joined.irq_a),
            self.bmc_wb.connect(bmc_decode.bus)
        ]

        # Target address decode
        m.submodules.target_decode = target_decode = WishboneDecoder(addr_width=16, data_width=8, granularity=8, features=["err"])

        target_ipmi_bus = ipmi_bt.target_wb
        target_ipmi_bus.memory_map = MemoryMap(addr_width=2, data_width=8)
        target_decode.add(target_ipmi_bus, addr=self.target_ipmi_addr)

        target_vuart_bus = vuart_joined.wb_b
        target_vuart_bus.memory_map = MemoryMap(addr_width=3, data_width=8)
        target_decode.add(target_vuart_bus, addr=self.target_vuart_addr)

        target_error_bus = self.error_wb
        target_error_bus.memory_map = MemoryMap(addr_width=2, data_width=8)
        # Generate a signal when we'd expect an ACK on the target bus
        ack_expected = Signal()
        m.d.sync += ack_expected.eq(self.target_wb.sel & self.target_wb.cyc &
                                   ~ack_expected)
        # Generate an error if no ack from ipmi_bt or vuart
        m.d.comb += self.error_wb.err.eq(0)
        with m.If (ack_expected):
            m.d.comb += self.error_wb.err.eq(~ipmi_bt.target_wb.ack &
                                             ~vuart_joined.wb_b.ack)
        target_decode.add(target_error_bus, addr=0x0)

        m.d.comb += [
            self.target_ipmi_irq.eq(ipmi_bt.target_irq),
            self.target_vuart_irq.eq(vuart_joined.irq_b),
            self.target_wb.connect(target_decode.bus)
        ]

        return m


if __name__ == "__main__":
    top = IOSpace()
    with open("io_map.v", "w") as f:
        f.write(verilog.convert(top))
