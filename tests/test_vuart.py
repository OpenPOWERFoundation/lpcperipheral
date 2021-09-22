import unittest

from nmigen.sim import Simulator

from lpcperipheral.vuart import VUart, RegEnum, LCR_DLAB
from .helpers import Helpers


class TestSum(unittest.TestCase, Helpers):
    def setUp(self):
        self.dut = VUart()

    def test_vuart(self):
        def bench():
            yield

            # Test reading and writing to LCR, MCR, MSR, SCR
            val = 0xF
            for r in (RegEnum.LCR, RegEnum.MCR, RegEnum.MSR, RegEnum.SCR):
                yield from self.wishbone_write(self.dut.wb, r, val)
                yield from self.wishbone_read(self.dut.wb, r, val)
                val = val + 1

            # Test writing to FCR (write only)
            yield from self.wishbone_write(self.dut.wb, RegEnum.IIR_FCR, val)

            # Test reading from LSR (THRE and TEMT bits should be set)
            yield from self.wishbone_read(self.dut.wb, RegEnum.LSR, 0b01100000)

            # Test reading from LSR with data ready (RD, THRE and TEMT bits should be set)
            yield self.dut.r_rdy.eq(1)
            yield from self.wishbone_read(self.dut.wb, RegEnum.LSR, 0b01100001)

            # Set DLAB bit
            yield from self.wishbone_write(self.dut.wb, RegEnum.LCR, 1 << LCR_DLAB)

            # Test reading and writing to DLL and DLM
            for r in (RegEnum.RXTX_DLL, RegEnum.IER_DLM):
                yield from self.wishbone_write(self.dut.wb, r, val)
                yield from self.wishbone_read(self.dut.wb, r, val)
                val = val + 1

            # Clear DLAB bit
            yield from self.wishbone_write(self.dut.wb, RegEnum.LCR, 0x00)

            # Test read from non empty FIFO
            yield self.dut.r_rdy.eq(1)
            yield self.dut.r_data.eq(0x45)

            yield from self.wishbone_read(self.dut.wb, RegEnum.RXTX_DLL, 0x45)
            self.assertEqual((yield self.dut.r_en), 1)
            self.assertEqual((yield self.dut.r_data), 0x45)
            yield
            self.assertEqual((yield self.dut.r_en), 0)

            # Test read from empty FIFO, check we don't attempt a read from the FIFO
            # and we return 0 over wishbone
            yield self.dut.r_rdy.eq(0)
            yield self.dut.r_data.eq(0x33)

            yield from self.wishbone_read(self.dut.wb, RegEnum.RXTX_DLL, 0x00)
            self.assertEqual((yield self.dut.r_en), 0)
            yield
            self.assertEqual((yield self.dut.r_en), 0)

            # Test write to non full FIFO
            yield self.dut.w_rdy.eq(1)

            yield from self.wishbone_write(self.dut.wb, RegEnum.RXTX_DLL, 0x65)
            self.assertEqual((yield self.dut.w_en), 1)
            self.assertEqual((yield self.dut.w_data), 0x65)
            yield
            self.assertEqual((yield self.dut.w_en), 0)

            # Test write to full FIFO
            yield self.dut.w_rdy.eq(0)

            yield from self.wishbone_write(self.dut.wb, RegEnum.RXTX_DLL, 0x77)
            self.assertEqual((yield self.dut.w_en), 0)

            # XXX Need to test ier lsr
            # IIR - read only
            # IER

        sim = Simulator(self.dut)
        sim.add_clock(1e-6)  # 1 MHz
        sim.add_sync_process(bench)
        with sim.write_vcd("test_vuart.vcd"):
            sim.run()

    def test_vuart_irqs(self):
        def bench():
            yield

            # Clear DLAB bit
            yield from self.wishbone_write(self.dut.wb, RegEnum.LCR, 0x00)

            # Test RX irq

            # No irqs if IER=0
            yield from self.wishbone_write(self.dut.wb, RegEnum.IER_DLM, 0x0)
            self.assertEqual((yield self.dut.irq), 0)
            yield from self.wishbone_read(self.dut.wb, RegEnum.IIR_FCR, 0b0001)

            # Set RX FIFO not empty
            yield self.dut.r_rdy.eq(1)
            yield self.dut.r_data.eq(0x45)
            yield
            self.assertEqual((yield self.dut.irq), 0)
            yield from self.wishbone_read(self.dut.wb, RegEnum.IIR_FCR, 0b0001)

            # RX irq if bit 1 is set
            yield from self.wishbone_write(self.dut.wb, RegEnum.IER_DLM, 0x1)
            yield
            self.assertEqual((yield self.dut.irq), 1)
            yield from self.wishbone_read(self.dut.wb, RegEnum.IIR_FCR, 0b0100)

            # No RX irq if IER=1 but empty RX FIFO
            yield self.dut.r_rdy.eq(0)
            yield self.dut.r_data.eq(0x00)
            yield
            self.assertEqual((yield self.dut.irq), 0)
            yield from self.wishbone_read(self.dut.wb, RegEnum.IIR_FCR, 0b0001)

            # Test TX irq

            # TX irq whenever IER bit 2 is set
            yield from self.wishbone_write(self.dut.wb, RegEnum.IER_DLM, 0x2)
            yield
            self.assertEqual((yield self.dut.irq), 1)
            yield from self.wishbone_read(self.dut.wb, RegEnum.IIR_FCR, 0b0010)

            # Test TX and RX irq together

            # Test RX irq priority over TX
            yield from self.wishbone_write(self.dut.wb, RegEnum.IER_DLM, 0x3)
            yield self.dut.r_rdy.eq(1)
            yield self.dut.r_data.eq(0x45)
            yield
            self.assertEqual((yield self.dut.irq), 1)
            yield from self.wishbone_read(self.dut.wb, RegEnum.IIR_FCR, 0b0100)

        sim = Simulator(self.dut)
        sim.add_clock(1e-6)  # 1 MHz
        sim.add_sync_process(bench)
        with sim.write_vcd("test_vuart_irqs.vcd"):
            sim.run()


if __name__ == '__main__':
    unittest.main()
