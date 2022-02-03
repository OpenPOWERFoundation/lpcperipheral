from amaranth import Signal, Elaboratable, Module
from amaranth.back import verilog
from amaranth.lib.fifo import SyncFIFOBuffered
from amaranth_soc.wishbone import Interface as WishboneInterface

from .vuart import VUart


class VUartJoined(Elaboratable):
    """
    Two Virtual UARTs connected together via a FIFO. Presents two 16550
    style interfaces over two wishbone slaves

    Parameters
    ----------

    Attributes
    ----------
    """
    def __init__(self, depth=8):
        self.depth = depth

        self.irq_a = Signal()
        self.wb_a = WishboneInterface(data_width=32, addr_width=3, granularity=8)

        self.irq_b = Signal()
        self.wb_b = WishboneInterface(data_width=8, addr_width=3, granularity=8)

    def elaborate(self, platform):
        m = Module()

        m.submodules.fifo_a = fifo_a = SyncFIFOBuffered(width=8, depth=self.depth)
        m.submodules.fifo_b = fifo_b = SyncFIFOBuffered(width=8, depth=self.depth)
        m.submodules.vuart_a = vuart_a = VUart()
        m.submodules.vuart_b = vuart_b = VUart()

        m.d.comb += [
            fifo_a.w_data.eq(vuart_a.w_data),
            vuart_a.w_rdy.eq(fifo_a.w_rdy),
            fifo_a.w_en.eq(vuart_a.w_en),
            vuart_a.r_data.eq(fifo_b.r_data),
            vuart_a.r_rdy.eq(fifo_b.r_rdy),
            fifo_b.r_en.eq(vuart_a.r_en),

            fifo_b.w_data.eq(vuart_b.w_data),
            vuart_b.w_rdy.eq(fifo_b.w_rdy),
            fifo_b.w_en.eq(vuart_b.w_en),
            vuart_b.r_data.eq(fifo_a.r_data),
            vuart_b.r_rdy.eq(fifo_a.r_rdy),
            fifo_a.r_en.eq(vuart_b.r_en),

            self.irq_a.eq(vuart_a.irq),
            self.irq_b.eq(vuart_b.irq),

            self.wb_a.connect(vuart_a.wb),
            self.wb_b.connect(vuart_b.wb),
        ]

        return m


if __name__ == "__main__":
    top = VUartJoined()
    with open("vuart_joined.v", "w") as f:
        f.write(verilog.convert(top))
