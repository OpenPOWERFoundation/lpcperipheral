import unittest

from amaranth.sim import Simulator

from lpcperipheral.io_space import IOSpace
from lpcperipheral.ipmi_bt import RegEnum, BMCRegEnum

from .helpers import Helpers


class TestSum(unittest.TestCase, Helpers):
    def setUp(self):
        self.dut = IOSpace()

    def test_io_space_vuart(self):
        def bench():
            yield

            # Look for TX empty bits
            yield from self.wishbone_read(self.dut.bmc_wb, (0x0 + (5 * 4)) // 4, 0x60)

            # Test 1 byte from BMC to target
            yield from self.wishbone_write(self.dut.bmc_wb, 0x0 // 4, 0x12)
            yield
            yield from self.wishbone_read(self.dut.target_wb, 0x3f8, 0x12)

            # Test 1 byte from target to BMC
            yield from self.wishbone_write(self.dut.target_wb, 0x3f8, 0x13)
            yield
            yield from self.wishbone_read(self.dut.bmc_wb, 0x0 // 4, 0x13)

            # Test 3 bytes from BMC to target
            yield from self.wishbone_write(self.dut.bmc_wb, 0x0 // 4, 0x15)
            yield from self.wishbone_write(self.dut.bmc_wb, 0x0 // 4, 0x16)
            yield from self.wishbone_write(self.dut.bmc_wb, 0x0 // 4, 0x17)
            yield from self.wishbone_read(self.dut.target_wb, 0x3f8, 0x15)
            yield from self.wishbone_read(self.dut.target_wb, 0x3f8, 0x16)
            yield from self.wishbone_read(self.dut.target_wb, 0x3f8, 0x17)

        sim = Simulator(self.dut)
        sim.add_clock(1e-6)  # 1 MHz
        sim.add_sync_process(bench)
        with sim.write_vcd("test_io_space_vuart.vcd"):
            sim.run()

    def test_io_space_ipmi_bt(self):
        def bench():
            yield

            # Test 1 byte from BMC to target via IPMI BT
            yield from self.wishbone_write(self.dut.bmc_wb, 0x1000//4 + BMCRegEnum.BMC2HOST_HOST2BMC, 0x43)
            yield
            yield from self.wishbone_read(self.dut.target_wb, 0xe4 + RegEnum.BMC2HOST_HOST2BMC, 0x43)

        sim = Simulator(self.dut)
        sim.add_clock(1e-6)  # 1 MHz
        sim.add_sync_process(bench)
        with sim.write_vcd("test_io_space_ipmi_bt.vcd"):
            sim.run()


if __name__ == '__main__':
    unittest.main()
