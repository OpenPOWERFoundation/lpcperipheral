# Typically LPC FW reads/writes directly access system memory of a
# CPU. These accesses need to be offset and windowed to ensure the LPC
# access can only access what the CPU wants it to.
#
# This modules takes a wishbone master from the LPC for firmware
# reads/writes and translates it into something that can be used for
# DMA access into another master wishbone bus. Base and mask registers
# (accessible via an IO wishbone bus) configure this

from nmigen import Elaboratable, Module, Signal
from nmigen_soc.wishbone import Interface as WishboneInterface
from nmigen_soc.csr import Multiplexer as CSRMultiplexer
from nmigen_soc.csr import Element as CSRElement
from nmigen_soc.csr.wishbone import WishboneCSRBridge
from nmigen.back import verilog


class LPC_Ctrl(Elaboratable):
    def __init__(self):
        self.io_wb = WishboneInterface(data_width=32, addr_width=2, granularity=8)

        self.lpc_wb = WishboneInterface(data_width=32, addr_width=26, granularity=8)
        self.dma_wb = WishboneInterface(data_width=32, addr_width=30, granularity=8)

    def elaborate(self, platform):
        m = Module()

        base_lo_csr = CSRElement(32, "rw")
        base_lo = Signal(32, reset=192*1024*1024)
        #  Leave space for upper 32 bits, unused for now
        base_hi_csr = CSRElement(32, "rw")
        mask_lo_csr = CSRElement(32, "rw")
        mask_lo = Signal(32, reset=0x3FFFFFF)
        #  Leave space for upper 32 bits, unused for now
        mask_hi_csr = CSRElement(32, "rw")

        m.submodules.mux = mux = CSRMultiplexer(addr_width=2, data_width=32)
        mux.add(base_lo_csr)
        mux.add(base_hi_csr)
        mux.add(mask_lo_csr)
        mux.add(mask_hi_csr)

        m.submodules.bridge = bridge = WishboneCSRBridge(mux.bus)

        m.d.comb += self.io_wb.connect(bridge.wb_bus)

        m.d.comb += [
            base_lo_csr.r_data.eq(base_lo),
            mask_lo_csr.r_data.eq(mask_lo),
        ]

        with m.If(base_lo_csr.w_stb):
            m.d.sync += base_lo.eq(base_lo_csr.w_data)
        with m.If(mask_lo_csr.w_stb):
            m.d.sync += mask_lo.eq(mask_lo_csr.w_data)

        m.d.comb += [
            self.lpc_wb.connect(self.dma_wb),
            # bask/mask are in bytes, so convert to wishbone addresses
            self.dma_wb.adr.eq((self.lpc_wb.adr & (mask_lo >> 2)) | (base_lo >> 2))
        ]

        return m


if __name__ == "__main__":
    top = LPC_Ctrl()
    with open("lpc_ctrl.v", "w") as f:
        f.write(verilog.convert(top))
