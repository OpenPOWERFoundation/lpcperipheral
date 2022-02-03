import unittest

from amaranth.sim import Simulator

from lpcperipheral.ipmi_bt import IPMI_BT, RegEnum, BMCRegEnum

from .helpers import Helpers


class TestSum(unittest.TestCase, Helpers):
    def setUp(self):
        self.dut = IPMI_BT(depth=64)

    def test_fifo(self):
        def bench():
            yield

            # Write one byte from target and read from BMC
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BMC2HOST_HOST2BMC, 0x12)
            yield
            yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BMC2HOST_HOST2BMC, 0x12)

            # Write 64 bytes from target and read from BMC
            for i in range(0, 64):
                yield from self.wishbone_write(self.dut.target_wb, RegEnum.BMC2HOST_HOST2BMC, i)
            for i in range(0, 64):
                yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BMC2HOST_HOST2BMC, i)

            # Write one byte from BMC and read from target
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BMC2HOST_HOST2BMC, 0x12)
            yield
            yield from self.wishbone_read(self.dut.target_wb, RegEnum.BMC2HOST_HOST2BMC, 0x12)

            # Write 64 bytes from BMC and read from target
            for i in range(0, 64):
                yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BMC2HOST_HOST2BMC, i)
            for i in range(0, 64):
                yield from self.wishbone_read(self.dut.target_wb, RegEnum.BMC2HOST_HOST2BMC, i)

            # Read from empty FIFO (should read 0)
            yield from self.wishbone_read(self.dut.target_wb, RegEnum.BMC2HOST_HOST2BMC, 0)
            yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BMC2HOST_HOST2BMC, 0)

            # Write to full FIFO (should do nothing)
            for i in range(0, 65):
                yield from self.wishbone_write(self.dut.target_wb, RegEnum.BMC2HOST_HOST2BMC, i)
                yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BMC2HOST_HOST2BMC, i)
            for i in range(0, 64):
                yield from self.wishbone_read(self.dut.target_wb, RegEnum.BMC2HOST_HOST2BMC, i)
                yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BMC2HOST_HOST2BMC, i)

            # Test reset of target fifo from target
            for i in range(0, 64):
                yield from self.wishbone_write(self.dut.target_wb, RegEnum.BMC2HOST_HOST2BMC, 0x5a)
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_CTRL, 0x1)
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BMC2HOST_HOST2BMC, 0x98)
            yield  # Need a cycle between writing the FIFO and reading it
            yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BMC2HOST_HOST2BMC, 0x98)
            yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BMC2HOST_HOST2BMC, 0)

            # Test reset of BMC fifo from BMC
            for i in range(0, 64):
                yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BMC2HOST_HOST2BMC, 0xa5)
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 0x1)
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BMC2HOST_HOST2BMC, 0x78)
            yield  # Need a cycle between writing the FIFO and reading it
            yield from self.wishbone_read(self.dut.target_wb, RegEnum.BMC2HOST_HOST2BMC, 0x78)
            yield from self.wishbone_read(self.dut.target_wb, RegEnum.BMC2HOST_HOST2BMC, 0)

        sim = Simulator(self.dut)
        sim.add_clock(1e-6)  # 1 MHz
        sim.add_sync_process(bench)
        with sim.write_vcd("test_ipmi_bt_fifo.vcd"):
            sim.run()

    def test_ctrl(self):
        def bench():
            # Init value for BT_CTRL
            yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 0)
            yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 0)

            # BT_CTRL bits 2, 5: target set, BMC clear
            for b in (2, 5):
                yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 0x0)
                # Write 1 on BMC, should do nothing
                yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << b)
                yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 0)
                # Write 1 from target
                yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_CTRL, 1 << b)
                # Check for 1 on target and bmc
                yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 1 << b)
                yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << b)
                # Write 1 on target, should do nothing
                yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_CTRL, 1 << b)
                yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 1 << b)
                # Write 1 on bmc, should clear bit
                yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << b)
                yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 0)

            # BT_CTRL bits 3, 4: BMC set, target clear
            for b in (3, 4):
                yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 0x0)
                # Write 1 on target, should do nothing
                yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_CTRL, 1 << b)
                yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 0)
                # Write 1 from BMC
                yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << b)
                # Check for 1 on target and bmc
                yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 1 << b)
                yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << b)
                # Write 1 on BMC, should do nothing
                yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << b)
                yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << b)
                # Write 1 on target, should clear bit
                yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_CTRL, 1 << b)
                yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 0)

            # BT_CTRL bit 6
            # Set bit, read from both target and BMC
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_CTRL, 1 << 6)
            yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 1 << 6)
            yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << 6)

            # Writing from BMC should do nothing
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << 6)
            yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 1 << 6)

            # Writing from target should clear
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_CTRL, 1 << 6)
            yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 0)

            # BT_CTRL bit 7
            # Set bit, read from both target and BMC
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << 7)
            yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 1 << 7)
            yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << 7)

            # Writing from target should do nothing
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_CTRL, 1 << 7)
            yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 1 << 7)

            # Writing from BMC should clear
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << 7)
            yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 0)

            # Read and write all bits in BT_CTRL from the target side
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_CTRL, 0xff)
            yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_CTRL, 0x64)


        sim = Simulator(self.dut)
        sim.add_clock(1e-6)  # 1 MHz
        sim.add_sync_process(bench)
        with sim.write_vcd("test_ipmi_bt_ctrl.vcd"):
            sim.run()

    def test_target_interrupts(self):
        def bench():
            # Test reading/writing BT_INTMASK from target. Only the bottom bit should be
            # writeable
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_INTMASK, 0xff)
            yield from self.wishbone_read(self.dut.target_wb, RegEnum.BT_INTMASK, 0x1)
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_INTMASK, 0x0)

            # With interrupts masked, shouldn't get an interrupt
            self.assertEqual((yield self.dut.target_irq), 0)
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << 3)
            self.assertEqual((yield self.dut.target_irq), 0)

            # With interrupt unmasked, should get interrupt, but only on a 0-1 transition
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_INTMASK, 1 << 0)
            self.assertEqual((yield self.dut.target_irq), 0)
            # Clear
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_CTRL, 1 << 3)
            self.assertEqual((yield self.dut.target_irq), 0)
            # and reassert
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << 3)
            self.assertEqual((yield self.dut.target_irq), 1)

            # Test the interrupt masking bit
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_INTMASK, 0x0)
            self.assertEqual((yield self.dut.target_irq), 0)
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_INTMASK, 0x1)
            self.assertEqual((yield self.dut.target_irq), 1)

            # Finally ack it
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_INTMASK, 0x2)
            self.assertEqual((yield self.dut.target_irq), 0)


        sim = Simulator(self.dut)
        sim.add_clock(1e-6)  # 1 MHz
        sim.add_sync_process(bench)
        with sim.write_vcd("test_ipmi_bt_target_interrupts.vcd"):
            sim.run()


    def test_bmc_interrupts(self):
        def bench():
            # Test reading/writing IRQ_MASK from BMC. Only the bottom two bits should be
            # writeable
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.IRQ_MASK, 0xff)
            yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.IRQ_MASK, 0x3)
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.IRQ_MASK, 0x0)

            # Test reading/writing IRQ_STATUS from BMC. Only the bottom two bits should be
            # writeable
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.IRQ_STATUS, 0xff)
            yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.IRQ_STATUS, 0x3)
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.IRQ_STATUS, 0x0)

            # With interrupts masked, shouldn't get an interrupt
            self.assertEqual((yield self.dut.bmc_irq), 0)
            yield from self.wishbone_write(self.dut.target_wb, BMCRegEnum.BT_CTRL, 1 << 2)
            self.assertEqual((yield self.dut.bmc_irq), 0)

            # With interrupt unmasked, should get interrupt, but only on a 0-1 transition
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.IRQ_MASK, 1 << 0)
            self.assertEqual((yield self.dut.bmc_irq), 0)
            # Clear
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.BT_CTRL, 1 << 2)
            self.assertEqual((yield self.dut.bmc_irq), 0)
            # and reassert
            yield from self.wishbone_write(self.dut.target_wb, RegEnum.BT_CTRL, 1 << 2)
            self.assertEqual((yield self.dut.bmc_irq), 1)

            # Test the interrupt masking bit
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.IRQ_MASK, 0x0)
            self.assertEqual((yield self.dut.bmc_irq), 0)
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.IRQ_MASK, 0x1)
            self.assertEqual((yield self.dut.bmc_irq), 1)
            yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.IRQ_STATUS, 0x1)

            # Finally ack it
            yield from self.wishbone_write(self.dut.bmc_wb, BMCRegEnum.IRQ_STATUS, 0x0)
            self.assertEqual((yield self.dut.bmc_irq), 0)
            yield from self.wishbone_read(self.dut.bmc_wb, BMCRegEnum.IRQ_STATUS, 0x0)

            # Test target busy goes low interrupt


        sim = Simulator(self.dut)
        sim.add_clock(1e-6)  # 1 MHz
        sim.add_sync_process(bench)
        with sim.write_vcd("test_ipmi_bt_target_interrupts.vcd"):
            sim.run()


if __name__ == '__main__':
    unittest.main()
