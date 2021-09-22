import unittest

from nmigen import Elaboratable, Module, Signal
from nmigen_soc.wishbone import Interface as WishboneInterface
from nmigen.sim import Simulator

from lpcperipheral.lpcperipheral import LPCPeripheral

from .ROM import ROM
from .helpers import Helpers

START_IO   = 0b0000
START_FWRD = 0b1101
START_FWWR = 0b1110

CYCLE_IOWRITE = 0b0010
CYCLE_IOREAD  = 0b0000

SYNC_READY      = 0b0000
SYNC_SHORT_WAIT = 0b0101
SYNC_LONG_WAIT  = 0b0110

LPC_IO_TESTS = 16
LPC_FW_TESTS = 2


class LPC_AND_ROM(Elaboratable):
    def __init__(self):
        self.bmc_wb = WishboneInterface(data_width=32, addr_width=14, granularity=8)

        # LPC bus
        self.lclk  = Signal()
        self.lframe = Signal()
        self.lad_in = Signal(4)
        self.lad_out = Signal(4)
        self.lad_en = Signal()
        self.lreset = Signal()

        # Interrupts
        self.bmc_vuart_irq = Signal()
        self.bmc_ipmi_irq = Signal()

        self.target_vuart_irq = Signal()
        self.target_ipmi_irq = Signal()

    def elaborate(self, platform):
        m = Module()

        m.submodules.lpc = lpc = LPCPeripheral()

        m.d.comb += [
            # BMC wishbone
            lpc.adr.eq(self.bmc_wb.adr),
            lpc.dat_w.eq(self.bmc_wb.dat_w),
            lpc.sel.eq(self.bmc_wb.sel),
            lpc.cyc.eq(self.bmc_wb.cyc),
            lpc.stb.eq(self.bmc_wb.stb),
            lpc.we.eq(self.bmc_wb.we),
            self.bmc_wb.dat_r.eq(lpc.dat_r),
            self.bmc_wb.ack.eq(lpc.ack),

            # LPC pins
            lpc.lclk.eq(self.lclk),
            lpc.lframe.eq(self.lframe),
            lpc.lad_in.eq(self.lad_in),
            self.lad_out.eq(lpc.lad_out),
            self.lad_en.eq(lpc.lad_en),
            lpc.lreset.eq(self.lreset),
        ]

        # Initialize ROM with the offset so we can easily determine if we are
        # reading from the right address
        data = range(128)
        m.submodules.rom = rom = ROM(data=data)

        m.d.comb += [
            # DMA wishbone to ROM
            rom.adr.eq(lpc.dma_adr),
            rom.dat_w.eq(lpc.dma_dat_w),
            rom.sel.eq(lpc.dma_sel),
            rom.cyc.eq(lpc.dma_cyc),
            rom.stb.eq(lpc.dma_stb),
            rom.we.eq(lpc.dma_we),
            lpc.dma_dat_r.eq(rom.dat_r),
            lpc.dma_ack.eq(rom.ack),
        ]

        return m

wb_read_go = 0

class TestSum(unittest.TestCase, Helpers):
    def setUp(self):
        self.dut = LPC_AND_ROM()

    def test_bench(self):
        def bench():
            global wb_read_go
            while wb_read_go == 0:
                yield
            yield from self.wishbone_read(self.dut.bmc_wb, 0x1014>>2, 0x65)
            yield from self.wishbone_read(self.dut.bmc_wb, 0x1014>>2, 0x48)

            wb_read_go = 0
            while wb_read_go == 0:
                yield
            yield from self.wishbone_read(self.dut.bmc_wb, 0x1010>>2, 0x4)

        def lbench():
            global wb_read_go
            wb_read_go = 0
            yield
            yield self.dut.lreset.eq(1)
            yield self.dut.lframe.eq(1)
            yield

            # Write 2 bytes to LPC IPMI-BT FIFO, read it on BMC wishbone
            yield from self.lpc_io_write(self.dut, 0xe5, 0x65)
            yield from self.lpc_io_write(self.dut, 0xe5, 0x48)
            wb_read_go = 1

            while wb_read_go == 1:
                yield

            # Test writing IPMI BT HOST2BMC attn bit, and reading it from the BMC
            yield from self.lpc_io_write(self.dut, 0xe4, 0x4)
            wb_read_go = 1

            #yield from self.lpc_fw_read(self.dut, 0xFFFFFFF, 1, 4)

            #yield from self.lpc_fw_read(self.dut, 1, 1, 4)
            #yield from self.lpc_fw_read(self.dut, 1, 1, 4)
            #yield from self.lpc_fw_read(self.dut, 1, 1, 4)

            #yield from self.lpc_fw_read(self.dut, 2, 2, 4)
            #yield from self.lpc_fw_read(self.dut, 2, 2, 4)
            #yield from self.lpc_fw_read(self.dut, 2, 2, 4)

        sim = Simulator(self.dut)
        # Make life easy by just running both clocks at same frequency
        sim.add_clock(1e-8)
        sim.add_clock(3e-8, domain="lclk")
        sim.add_clock(3e-8, domain="lclkrst")
        #sim._engine.add_clock_process(self.dut.lclk, phase=None, period=1e-8)
        sim.add_sync_process(lbench, domain="lclk")
        sim.add_sync_process(bench, domain="sync")

        with sim.write_vcd("test_lpc.vcd"):
            sim.run()

if __name__ == '__main__':
    unittest.main()
