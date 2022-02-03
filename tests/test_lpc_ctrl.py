import unittest

from amaranth import Elaboratable, Module
from amaranth_soc.wishbone import Interface as WishboneInterface
from amaranth.sim import Simulator

from lpcperipheral.lpc_ctrl import LPC_Ctrl

from .ROM import ROM
from .helpers import Helpers


class LPC_AND_ROM(Elaboratable):
    def __init__(self):
        self.io_wb = WishboneInterface(data_width=32, addr_width=2, granularity=8)
        self.lpc_wb = WishboneInterface(data_width=32, addr_width=26, granularity=8)

    def elaborate(self, platform):
        m = Module()

        m.submodules.ctrl = ctrl = LPC_Ctrl()

        m.d.comb += [
            self.io_wb.connect(ctrl.io_wb),
            self.lpc_wb.connect(ctrl.lpc_wb),
        ]

        # Initialize ROM with the offset so we can easily determine if we are
        # reading from the right address
        data = range(128)
        m.submodules.rom = rom = ROM(data=data)
        m.d.comb += ctrl.dma_wb.connect(rom)

        return m


class TestSum(unittest.TestCase, Helpers):
    def setUp(self):
        self.dut = LPC_AND_ROM()

    def test_read_write(self):
        def bench():
            # base register, offset 0
            # Note CSRs have an extra cycle before ack, hence delay=2
            yield from self.wishbone_write(self.dut.io_wb, 0, 0x12345678, delay=2)
            yield
            yield from self.wishbone_read(self.dut.io_wb, 0, 0x12345678, delay=2)

            # mask register, offset 2
            yield from self.wishbone_write(self.dut.io_wb, 2, 0xBADC0FFE, delay=2)
            yield
            yield from self.wishbone_read(self.dut.io_wb, 2, 0xBADC0FFE, delay=2)

        sim = Simulator(self.dut)
        sim.add_clock(1e-6)  # 1 MHz
        sim.add_sync_process(bench)
        with sim.write_vcd("test_lpc_ctrl_read_write.vcd"):
            sim.run()

    def test_base_offset(self):
        def bench():
            yield

            # No offset, don't mask off any bits
            # Note CSRs have an extra cycle before ack, hence delay=2
            yield from self.wishbone_write(self.dut.io_wb, 0, 0x0, delay=2)
            yield from self.wishbone_write(self.dut.io_wb, 0x2, 0xffffffff, delay=2)

            for i in range(64):
                yield from self.wishbone_read(self.dut.lpc_wb, i, i)

            # Apply offset and test. The base/mask registers are in bytes
            # So we have to convert from wishbone addresses (assuming a 32
            # bit wishbone, multiply by 4)
            base = 32  # In wishbone units
            yield from self.wishbone_write(self.dut.io_wb, 0, base * 4, delay=2)
            for i in range(32):
                yield from self.wishbone_read(self.dut.lpc_wb, i, i + base, delay=2)

            # Apply mask and test
            yield from self.wishbone_write(self.dut.io_wb, 0x2, 0xf * 4, delay=2)
            for i in range(32):
                yield from self.wishbone_read(self.dut.lpc_wb, i, ((i % 0x10) + base), delay=2)

        sim = Simulator(self.dut)
        sim.add_clock(1e-6)  # 1 MHz
        sim.add_sync_process(bench)
        with sim.write_vcd("test_lpc_ctrl_base_offset.vcd"):
            sim.run()


if __name__ == '__main__':
    unittest.main()
