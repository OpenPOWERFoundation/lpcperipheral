import unittest
import random

from nmigen.sim import Simulator

from lpcperipheral.lpc2wb import lpc2wb

from .helpers import Helpers

LPC_IO_TESTS = 16
LPC_FW_TESTS = 128

addr = 0
data = 0
size = 0

class TestSum(unittest.TestCase, Helpers):
    def setUp(self):
        self.dut = lpc2wb()

    def test_bench(self):

        def io_bench():
            global addr
            global data
            # ACK wishbone bus
            # check data on writes and send data back on reads
            for i in range(LPC_IO_TESTS):
                # wait for wishbone cycle
                while (yield self.dut.io_wb.cyc) == 0:
                    yield
                self.assertEqual((yield self.dut.io_wb.adr), addr)
                if (yield self.dut.io_wb.we) == 1:
                    # check data for LPC writes
                    # print("Checking write: addr:%x" % (io_addr))
                    self.assertEqual((yield self.dut.io_wb.dat_w),
                                     data)
                else:
                    # End back hashed data for LPC reads
                    # print("Sending read: addr:%x" % (io_addr))
                    yield self.dut.io_wb.dat_r.eq(data)
                yield self.dut.io_wb.ack.eq(1)
                yield
                yield self.dut.io_wb.ack.eq(0)
                yield

        def fw_bench():
            global addr
            global data
            global size
            # ACK wishbone bus
            # check data on writes and send data back on reads
            for i in range(LPC_FW_TESTS):
                # wait for wishbone cycle
                while (yield self.dut.fw_wb.cyc) == 0:
                    yield
                yield
                yield
                yield
                self.assertEqual((yield self.dut.fw_wb.adr), addr >> 2) # 4 byte word addr
                if (yield self.dut.fw_wb.we) == 1:
                    # check data for LPC writes
#                    print("Checking FW write: addr:%x" % (addr))
                    wb = yield self.dut.fw_wb.dat_w
                    if (size == 1):
                        wb = wb >> (8 * (addr & 0x3))
                        d = data & 0xff
                        sel = 1 << (addr & 3)
                    if (size == 2):
                        wb = wb >> (8 * (addr & 0x2))
                        d = data & 0xffff
                        sel = 0b0011 << (addr & 0x2)
                    if (size == 4):
                        d = data
                        sel = 0b1111
                    self.assertEqual(d, wb)

                else: # reads
                    # End back hashed data for LPC reads
                    if (size == 1):
                        d = data & 0xff
                        d = d << (8 * (addr & 0x3))
                        yield self.dut.fw_wb.dat_r.eq(d)
                        sel = 1 << (addr & 3)
                    if (size == 2):
                        d = data & 0xffff
                        d = d << (8 * (addr & 0x2))
                        sel = 0b0011 << (addr & 0x2)
                        yield self.dut.fw_wb.dat_r.eq(d)
                    if (size == 4):
                        yield self.dut.fw_wb.dat_r.eq(data)
                        sel = 0b1111
                self.assertEqual((yield self.dut.fw_wb.sel), sel)

                yield self.dut.fw_wb.ack.eq(1)
                yield
                yield self.dut.fw_wb.ack.eq(0)
                yield

        def lpc_bench():
            global addr
            global data
            global size

            # lframe = 1 shouldn't move
            yield self.dut.lframe.eq(1)
            yield self.dut.lreset.eq(1)
            for _ in range(4):
                yield

            # Do a bunch of partial transactions at the start to see
            # if it locks up the bus for later transactions
            for i in range(8):
                yield from self.lpc_io_read_partial(self.dut, i)

            for i in range(LPC_FW_TESTS):
                addr = random.randrange(0x10000000)
                data = random.randrange(0x100000000)
                size = 2**random.randrange(3) # 1,2,4
                addrmask = 0xffffffff & ~(size - 1)
                addr = addr & addrmask # align address
                if random.randrange(2):
                    yield from self.lpc_fw_write(self.dut, addr, data, size)
                else:
                    yield from self.lpc_fw_read(self.dut, addr, data, size)
                yield
                yield

            for _ in range(10):
                yield

            # do a bunch of random read and write tests
            for i in range(LPC_IO_TESTS):
                addr = random.randrange(0x10000)
                data = random.randrange(0x100)
                if random.randrange(2):
                    yield from self.lpc_io_write(self.dut, addr, data)
                else:
                    yield from self.lpc_io_read(self.dut, addr, data)
                yield

            yield


        sim = Simulator(self.dut)
        sim.add_clock(1e-8)  # 100 MHz systemclock
        sim.add_clock(3e-8, domain="lclk")  # 30 MHz LPC clock
        sim.add_clock(3e-8, domain="lclkrst")  # 30 MHz LPC clock
        sim.add_sync_process(lpc_bench, domain="lclk")
        sim.add_sync_process(io_bench, domain="sync")
        sim.add_sync_process(fw_bench, domain="sync")
        with sim.write_vcd("lpc2wb_lbench.vcd"):
            sim.run()


if __name__ == '__main__':
    unittest.main()
