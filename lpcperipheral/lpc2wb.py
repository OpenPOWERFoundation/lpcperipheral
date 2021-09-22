#
# This is an LPC slave to wishbone interface
#
#             LPC Clock         |       System Clock
#
#         +---------+     +------------+     +--------+
#   LPC   |         |     |   ASYNC    |     |        | Wishbone
#   pins  |         +---->|  FIFO WR   +---->|        | IO Space
#         |   LPC   |     |            |     |        |<-------->
# <------>|  Front  |     +------------+     | LOGIC  |
#         |         |                        |        |
#         |         |     +------------+     |        | Wishbone
#         |         |     |   ASYNC    |     |        | FW Space
#         |         |<----+  FIFO RD   |<----+        |<-------->
#         |         |     |            |     |        |
#         +---------+     +------------+     +--------+
#
# It takes the lpcfront and and turns it into IO and FW wishbone
# interfaces. The lpcfront operates on the lpc clock domain and the
# wishbone interfaces operate on the standard "sync" domain.
#
# To cross the clock domains async fifos are used. The write fifo
# takes write commands from the lpc interface. The read fifo gets
# information back to respond to these write commands.
#
# The write fifo turns the write commands into either an IO or FW
# wishbone transaction. The read fifo takes the wishbone transaction
# reponses and sends them back to the LPC.
#
# If an address doesn't exist on the wishbone interfaces (common on
# the IO bus), the wishbone interface asserts the err signal (rather
# than the ack). When this occurs the read fifo send an error back to
# the LPC.
#

from nmigen import Signal, Elaboratable, Module
from nmigen import ClockSignal, Cat, DomainRenamer, ResetSignal, ResetInserter
from nmigen.lib.fifo import AsyncFIFO
from nmigen_soc.wishbone import Interface as WishboneInterface
from nmigen.back import verilog

from .lpcfront import lpcfront, LPCCycletype, LPC_FW_DATA_WIDTH, LPC_FW_ADDR_WIDTH, LPC_IO_DATA_WIDTH, LPC_IO_ADDR_WIDTH


class lpc2wb(Elaboratable):

    def __init__(self):

        # LPC clock pin
        self.lclk  = Signal()
        self.lframe = Signal()
        self.lad_in = Signal(4)
        self.lad_out = Signal(4)
        self.lad_en = Signal()
        self.lreset = Signal()

        self.io_wb = WishboneInterface(data_width=LPC_IO_DATA_WIDTH,
                                       addr_width=LPC_IO_ADDR_WIDTH,
                                       granularity=8,
                                       features = ["err"])
        # 32 bit bus, so address only need to address words
        self.fw_wb = WishboneInterface(data_width=LPC_FW_DATA_WIDTH,
                                       addr_width=LPC_FW_ADDR_WIDTH - 2,
                                       granularity=8)

    def elaborate(self, platform):
        m = Module()

        # hook up lclk port to lclk domain
        m.d.comb += ClockSignal("lclk").eq(self.lclk)

        # Use main reset to reset lclk domain
        m.d.comb += ResetSignal("lclk").eq(ResetSignal())

        # create lpc front end wth right clock domain
        m.submodules.lpc = lpc = DomainRenamer("lclk")(lpcfront())

        wr_data = Signal(lpc.wrcmd.data.width)
        wr_addr = Signal(lpc.wrcmd.addr.width)
        wr_cmd = Signal(lpc.wrcmd.cmd.width)
        wr_size = Signal(lpc.wrcmd.size.width)
        wr_rdy = Signal()

        # hook up lclk port to lclk domain
        m.d.comb += ClockSignal("lclkrst").eq(self.lclk)
        # Use main reset to reset lclk domain
        m.d.comb += ResetSignal("lclkrst").eq(lpc.wrcmd.rst)

        # hook up external lpc interface
        m.d.comb += lpc.lframe.eq(self.lframe)
        m.d.comb += lpc.lreset.eq(self.lreset)
        m.d.comb += lpc.lad_in.eq(self.lad_in)
        m.d.comb += self.lad_en.eq(lpc.lad_en)
        m.d.comb += self.lad_out.eq(lpc.lad_out)

        # We have two fifo
        # 1) fifowr for getting commands from the LPC and transferring them
        #     to the wishbone. This has address for writes and reads, data
        #     for writes and cmd (IO read/write)
        # 2) fiford for getting read data from the wishbone back to the LPC.
        fifowr = AsyncFIFO(width=lpc.wrcmd.width(), depth=2,
                      r_domain="sync",
                      w_domain="lclkrst")
        m.submodules += fifowr
        fiford = AsyncFIFO(width=lpc.rdcmd.width(), depth=2,
                      r_domain="lclkrst",
                      w_domain="sync")
        m.submodules += fiford
        # lpc clock side
        m.d.comb += fifowr.w_data[ 0:32].eq(lpc.wrcmd.data)
        m.d.comb += fifowr.w_data[32:60].eq(lpc.wrcmd.addr)
        m.d.comb += fifowr.w_data[60:62].eq(lpc.wrcmd.cmd)
        m.d.comb += fifowr.w_data[62:64].eq(lpc.wrcmd.size)
        m.d.comb += lpc.wrcmd.rdy.eq(fifowr.w_rdy)
        m.d.comb += fifowr.w_en.eq(lpc.wrcmd.en)
        # system clock side
        m.d.comb += wr_data.eq(fifowr.r_data[ 0:32])  # sliced as above
        m.d.comb += wr_addr.eq(fifowr.r_data[32:60])  # sliced as above
        m.d.comb += wr_cmd.eq (fifowr.r_data[60:62])  # sliced as above
        m.d.comb += wr_size.eq(fifowr.r_data[62:64])  # sliced as above
        m.d.comb += wr_rdy.eq(fifowr.r_rdy)
        m.d.comb += fifowr.r_en.eq(0) # See below for wishbone acks

        # turn fifowr into IO wishbone master
        m.d.comb += self.io_wb.adr.eq(wr_addr[0:16])
        m.d.comb += self.io_wb.dat_w.eq(wr_data[0:8])
        m.d.comb += self.io_wb.sel.eq(1)
        m.d.comb += self.io_wb.we.eq(wr_cmd == LPCCycletype.IOWR)
        with m.If ((wr_cmd == LPCCycletype.IORD) | (wr_cmd == LPCCycletype.IOWR)):
            # The fiford should always be ready here but check anyway
            m.d.comb += self.io_wb.cyc.eq(wr_rdy & fiford.w_rdy)
            m.d.comb += self.io_wb.stb.eq(wr_rdy & fiford.w_rdy)
        # turn fifowr into FW wishbone master
        m.d.comb += self.fw_wb.adr.eq(wr_addr[2:28])
        # data comes in the MSB so we need to shift it down for smaller sizes
        m.d.comb += self.fw_wb.dat_w.eq(wr_data)
        with m.If (wr_size == 3):
            m.d.comb += self.fw_wb.sel.eq(0b1111)
        with m.If (wr_size == 1):
            with m.If (wr_addr[1] == 0b0):
                m.d.comb += self.fw_wb.sel.eq(0b0011)
            with m.If (wr_addr[1] == 0b1):
                m.d.comb += self.fw_wb.sel.eq(0b1100)
                m.d.comb += self.fw_wb.dat_w.eq(wr_data << 16)
        with m.If (wr_size == 0):
            with m.If (wr_addr[0:2] == 0b00):
                m.d.comb += self.fw_wb.sel.eq(0b0001)
            with m.If (wr_addr[0:2] == 0b01):
                m.d.comb += self.fw_wb.sel.eq(0b0010)
                m.d.comb += self.fw_wb.dat_w.eq(wr_data << 8)
            with m.If (wr_addr[0:2] == 0b10):
                m.d.comb += self.fw_wb.sel.eq(0b0100)
                m.d.comb += self.fw_wb.dat_w.eq(wr_data << 16)
            with m.If (wr_addr[0:2] == 0b11):
                m.d.comb += self.fw_wb.sel.eq(0b1000)
                m.d.comb += self.fw_wb.dat_w.eq(wr_data << 24)
        m.d.comb += self.fw_wb.we.eq(wr_cmd == LPCCycletype.FWWR)
        with m.If ((wr_cmd == LPCCycletype.FWRD) | (wr_cmd == LPCCycletype.FWWR)):
            # The fiford should always be ready here but check anyway
            m.d.comb += self.fw_wb.cyc.eq(wr_rdy & fiford.w_rdy)
            m.d.comb += self.fw_wb.stb.eq(wr_rdy & fiford.w_rdy)
        # Arbitrate the acks back into the fifo
        with m.If ((wr_cmd == LPCCycletype.IORD) | (wr_cmd == LPCCycletype.IOWR)):
            m.d.comb += fifowr.r_en.eq(self.io_wb.ack | self.io_wb.err)
            m.d.comb += fiford.w_data[32].eq(self.io_wb.err)
        with m.If ((wr_cmd == LPCCycletype.FWRD) | (wr_cmd == LPCCycletype.FWWR)):
            m.d.comb += fifowr.r_en.eq(self.fw_wb.ack)
            m.d.comb += fiford.w_data[32].eq(0)

        # sending data back from IO/FW wishbones to fiford
        with m.If (wr_cmd == LPCCycletype.IORD):
            m.d.comb += fiford.w_data[0:32].eq(self.io_wb.dat_r)
        with m.Elif (wr_cmd == LPCCycletype.FWRD):
            m.d.comb += fiford.w_data[0:32].eq(self.fw_wb.dat_r)
            with m.If (wr_size == 1):
                with m.If (wr_addr[1] == 0b1):
                    m.d.comb += fiford.w_data[0:16].eq(self.fw_wb.dat_r[16:32])
            with m.If (wr_size == 0):
                with m.If (wr_addr[0:2] == 0b01):
                    m.d.comb += fiford.w_data[0:8].eq(self.fw_wb.dat_r[8:16])
                with m.If (wr_addr[0:2] == 0b10):
                    m.d.comb += fiford.w_data[0:8].eq(self.fw_wb.dat_r[16:24])
                with m.If (wr_addr[0:2] == 0b11):
                    m.d.comb += fiford.w_data[0:8].eq(self.fw_wb.dat_r[24:32])
        m.d.comb += fiford.w_en.eq(self.io_wb.ack | self.fw_wb.ack | self.io_wb.err)

        # lpc side of read fiford
        m.d.comb += fiford.r_en.eq(lpc.rdcmd.en)
        m.d.comb += lpc.rdcmd.data.eq(fiford.r_data[0:32])
        m.d.comb += lpc.rdcmd.error.eq(fiford.r_data[32])
        m.d.comb += lpc.rdcmd.rdy.eq(fiford.r_rdy)

        return m


if __name__ == "__main__":
    top = lpc2wb()
    with open("lpc2wb.v", "w") as f:
        f.write(verilog.convert(top))
