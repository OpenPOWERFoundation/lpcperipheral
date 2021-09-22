import unittest

from nmigen.sim import Simulator

from lpcperipheral.vuart import RegEnum
from lpcperipheral.vuart_joined import VUartJoined

from .helpers import Helpers

class TestSum(unittest.TestCase, Helpers):
    def setUp(self):
        self.dut = VUartJoined(depth=2)

    def test_vuart_joined(self):
        def bench():
            yield

            # Try writing one byte and reading it from the other VUart
            yield from self.wishbone_write(self.dut.wb_a, RegEnum.RXTX_DLL, 0x65)
            yield  # SyncFIFOBuffered needs one cycle for write -> read ready
            yield from self.wishbone_read(self.dut.wb_b, RegEnum.RXTX_DLL, 0x65)

            # Same test from other VUart
            yield from self.wishbone_write(self.dut.wb_b, RegEnum.RXTX_DLL, 0x79)
            yield  # SyncFIFOBuffered needs one cycle for write -> read ready
            yield from self.wishbone_read(self.dut.wb_a, RegEnum.RXTX_DLL, 0x79)

            # Try reading from an empty FIFO
            yield from self.wishbone_read(self.dut.wb_a, RegEnum.RXTX_DLL, 0x0)
            yield from self.wishbone_read(self.dut.wb_b, RegEnum.RXTX_DLL, 0x0)

            # Write 2 bytes and read them
            yield from self.wishbone_write(self.dut.wb_a, RegEnum.RXTX_DLL, 0x45)
            # SyncFIFOBuffered drops w_rdy for 1 cycle on almost (n-1)
            # full, likely because there is a separate 1 entry read
            # buffer. Bug?
            yield
            yield from self.wishbone_write(self.dut.wb_a, RegEnum.RXTX_DLL, 0x32)
            yield from self.wishbone_read(self.dut.wb_b, RegEnum.RXTX_DLL, 0x45)
            yield from self.wishbone_read(self.dut.wb_b, RegEnum.RXTX_DLL, 0x32)

            # Write 3 bytes and read 2 (We configured the FIFO to be 2 deep)
            yield from self.wishbone_write(self.dut.wb_a, RegEnum.RXTX_DLL, 0x11)
            # (n-1) full issue as above
            yield
            yield from self.wishbone_write(self.dut.wb_a, RegEnum.RXTX_DLL, 0x22)
            # (n-1) full issue as above
            yield
            yield from self.wishbone_write(self.dut.wb_a, RegEnum.RXTX_DLL, 0x33)
            yield from self.wishbone_read(self.dut.wb_b, RegEnum.RXTX_DLL, 0x11)
            yield from self.wishbone_read(self.dut.wb_b, RegEnum.RXTX_DLL, 0x22)
            yield from self.wishbone_read(self.dut.wb_b, RegEnum.RXTX_DLL, 0x00)

        sim = Simulator(self.dut)
        sim.add_clock(1e-6)  # 1 MHz
        sim.add_sync_process(bench)
        with sim.write_vcd("vuart_joined.vcd"):
            sim.run()


if __name__ == '__main__':
    unittest.main()
