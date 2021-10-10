from enum import Enum, unique

from nmigen import Signal, Elaboratable, Module, Cat
from nmigen.back import verilog

from .io_space import IOSpace
from .lpc2wb import lpc2wb
from .lpc_ctrl import LPC_Ctrl


@unique
class StateEnum(Enum):
    IDLE = 0
    ACK = 1


class LPCPeripheral(Elaboratable):
    """
    Parameters
    ----------

    Attributes
    ----------
    """
    def __init__(self):
        # BMC wishbone. We dont use a Record because we want predictable
        # signal names so we can hook it up to VHDL/Verilog
        self.adr = Signal(14)
        self.dat_w = Signal(32)
        self.dat_r = Signal(32)
        self.sel = Signal()
        self.cyc = Signal()
        self.stb = Signal()
        self.we = Signal()
        self.ack = Signal()

        # DMA wishbone
        self.dma_adr = Signal(30)
        self.dma_dat_w = Signal(32)
        self.dma_dat_r = Signal(32)
        self.dma_sel = Signal(4)
        self.dma_cyc = Signal()
        self.dma_stb = Signal()
        self.dma_we = Signal()
        self.dma_ack = Signal()

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

        m.submodules.io = io = IOSpace()
        m.submodules.lpc = lpc = lpc2wb()
        m.submodules.lpc_ctrl = lpc_ctrl = LPC_Ctrl()

        m.d.comb += [
            # BMC wishbone
            io.bmc_wb.adr.eq(self.adr),
            io.bmc_wb.dat_w.eq(self.dat_w),
            io.bmc_wb.sel.eq(self.sel),
            io.bmc_wb.cyc.eq(self.cyc),
            io.bmc_wb.stb.eq(self.stb),
            io.bmc_wb.we.eq(self.we),
            self.dat_r.eq(io.bmc_wb.dat_r),
            self.ack.eq(io.bmc_wb.ack),

            # target wishbone
            io.target_wb.adr.eq(lpc.io_wb.adr),
            io.target_wb.dat_w.eq(lpc.io_wb.dat_w),
            io.target_wb.sel.eq(lpc.io_wb.sel),
            io.target_wb.cyc.eq(lpc.io_wb.cyc),
            io.target_wb.stb.eq(lpc.io_wb.stb),
            io.target_wb.we.eq(lpc.io_wb.we),
            lpc.io_wb.dat_r.eq(io.target_wb.dat_r),
            lpc.io_wb.ack.eq(io.target_wb.ack),
            lpc.io_wb.err.eq(io.target_wb.err),

            # LPC CTRL to DMA wishbone
            self.dma_adr.eq(lpc_ctrl.dma_wb.adr),
            self.dma_dat_w.eq(lpc_ctrl.dma_wb.dat_w),
            self.dma_sel.eq(lpc_ctrl.dma_wb.sel),
            self.dma_cyc.eq(lpc_ctrl.dma_wb.cyc),
            self.dma_stb.eq(lpc_ctrl.dma_wb.stb),
            self.dma_we.eq(lpc_ctrl.dma_wb.we),
            lpc_ctrl.dma_wb.dat_r.eq(self.dma_dat_r),
            lpc_ctrl.dma_wb.ack.eq(self.dma_ack),

            # LPC to LPC CTRL DMA wishbone
            lpc.fw_wb.connect(lpc_ctrl.lpc_wb),

            # LPC CTRL I/O wishbone
            io.lpc_ctrl_wb.connect(lpc_ctrl.io_wb),

            # LPC
            lpc.lclk.eq(self.lclk),
            lpc.lframe.eq(self.lframe),
            lpc.lad_in.eq(self.lad_in),
            self.lad_out.eq(lpc.lad_out),
            self.lad_en.eq(lpc.lad_en),
            lpc.lreset.eq(self.lreset),

            # Interrupts
            self.bmc_vuart_irq.eq(io.bmc_vuart_irq),
            self.bmc_ipmi_irq.eq(io.bmc_ipmi_irq),
            self.target_vuart_irq.eq(io.target_vuart_irq),
            self.target_ipmi_irq.eq(io.target_ipmi_irq),
        ]

        return m


if __name__ == "__main__":
    top = LPCPeripheral()
    with open("lpcperipheral.v", "w") as f:
        f.write(verilog.convert(top, ports=[
            top.adr, top.dat_w, top.dat_r, top.sel, top.cyc, top.stb,
            top.we, top.ack, top.dma_adr, top.dma_dat_w, top.dma_dat_r,
            top.dma_sel, top.dma_cyc, top.dma_stb, top.dma_we, top.dma_ack,
            top.lclk, top.lframe, top.lad_in,
            top.lad_out, top.lad_en, top.lreset, top.bmc_vuart_irq,
            top.bmc_ipmi_irq, top.target_vuart_irq, top.target_ipmi_irq], name="lpc_top"))
