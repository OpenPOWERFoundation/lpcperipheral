#
# This is a LPC slave front end. It runs the LPC statemachine for FW
# and IO Read and write cycles. It's clocked off the LPC lclk and no
# other clock is needed. The LPC/front end is just the
# LAD/lframe/lreset lines.
#
# This collects address/data/cmd info and presents it to a back end
# interface which is split into a write and read interface. Incoming
# LPC transactions are presented on the write interface via
# LPCWRCMDInterface. The back end reponds via the read interface via
# LPCRDCMDInterface. Both of these interfaces use the LPC clock.
#
# To ensure that the back end can respond to requests, the LPC sync
# cycle is held in a long wait until the be back end responds. If
# there is an error in the back end (eg an address doesn't exist),
# the error signal can be asserted, and the SYNC cycle will ERROR and
# then release the LAD lines. If there is no error, the SYNC will
# respond with READY and finish the LPC transaction. This happens on
# both LPC reads and writes.
#
# DMA and MEM read/write cycles are not supported currently. LPC
# interrupts (SERIRQ) is also not supported currently
#

from enum import Enum, unique
from nmigen import Signal, Elaboratable, Module, unsigned, Cat
from nmigen.back import verilog
import math

@unique
class LPCStates(Enum):
    START       = 0
    CYCLETYPE   = 1 # IO
    IOADDR      = 2
    FWIDSEL     = 3 # FW
    FWADDR      = 4
    FWMSIZE     = 5
    RDTAR1      = 6 # Reads
    RDSYNC      = 7
    RDDATA      = 8
    WRDATA      = 9 # Writes
    WRTAR1      = 10
    WRSYNC      = 11
    TAR2        = 12 # End common for Reads and Writes

@unique
class LPCCycletype(Enum):
    IORD          = 0
    IOWR          = 1
    FWRD          = 2
    FWWR          = 3

class LPCStartType():
    MEMIODMA      = 0b0000
    FWRD          = 0b1101
    FWWR          = 0b1110

class LPCSyncType():
    READY         = 0b0000
    SHORT_WAIT    = 0b0101
    LONG_WAIT     = 0b0110
    ERROR         = 0b1010

LPC_IO_DATA_WIDTH = 8
LPC_IO_ADDR_WIDTH = 16
LPC_FW_DATA_WIDTH = 32
LPC_FW_ADDR_WIDTH = 28

class LPCWRCMDInterface():
    def __init__(self, *, addr_width, data_width):
        self.addr = Signal(addr_width)
        self.data = Signal(data_width)
        self.cmd = Signal(LPCCycletype)
        self.size = Signal(2) # upto 4 bytes
        self.rdy = Signal()
        self.en = Signal()
        self.rst = Signal()

    # width of fifo needed to transport this
    def width(self):
        return self.addr.width + self.data.width + self.cmd.width + self.size.width

class LPCRDCMDInterface():
    def __init__(self, *, data_width):
        self.data = Signal(data_width)
        self.error = Signal()
        self.rdy = Signal()  # data is ready
        self.en = Signal()  # data has been read
        self.rst = Signal()

    # width of fifo needed to transport this
    def width(self):
        return self.data.width + self.error.width

class lpcfront(Elaboratable):
    """
    LPC slave
    """
    def __init__(self):
        # Ports
        self.lframe = Signal()
        self.lad_in = Signal(4)
        self.lad_out = Signal(4)
        self.lad_en = Signal()
        self.lreset = Signal()

        # synthetic tristate signals
        self.lad_tri = Signal(4)

        self.wrcmd = LPCWRCMDInterface(addr_width=LPC_FW_ADDR_WIDTH,
                                       data_width=LPC_FW_DATA_WIDTH)
        self.rdcmd = LPCRDCMDInterface(data_width=LPC_FW_DATA_WIDTH)

    def elaborate(self, platform):
        m = Module()

        state = Signal(LPCStates)
        statenext = Signal(LPCStates)
        cycletype = Signal(LPCCycletype)
        # FW data is 32 bites with 4 bits per cycle = 8 cycles
        cyclecount = Signal(math.ceil(math.log2(LPC_FW_DATA_WIDTH/4)))
        addr = Signal(LPC_FW_ADDR_WIDTH)
        data = Signal(LPC_FW_DATA_WIDTH)
        size = Signal(unsigned(2)) # 1, 2 or 4 bytes

        lframesync = Signal()

        # fifo interface
        m.d.comb += self.wrcmd.addr.eq(addr)
        m.d.comb += self.wrcmd.data.eq(data)
        m.d.comb += self.wrcmd.size.eq(size)
        m.d.comb += self.wrcmd.en.eq(0)  # default, also set below
        m.d.comb += self.rdcmd.en.eq(0)  # default, also set below

        m.d.sync += state.eq(statenext)  # state machine
        m.d.comb += self.lad_en.eq(0)  # set below also
        # run the states
        m.d.comb += statenext.eq(state)  # stay where we are by default
        with m.Switch(state):
            # with m.Case(LPCStates.START):
            # this is handled at the end as an override since lframe
            # can be aserted at any point

            with m.Case(LPCStates.CYCLETYPE):
                m.d.comb += statenext.eq(LPCStates.IOADDR)
                m.d.sync += cyclecount.eq(3)

                with m.Switch(self.lad_in):
                    with m.Case("000-"):
                        m.d.sync += cycletype.eq(LPCCycletype.IORD)
                    with m.Case("001-"):
                        m.d.sync += cycletype.eq(LPCCycletype.IOWR)
                    with m.Default():
                        m.d.comb += statenext.eq(LPCStates.START) # Bail

            with m.Case(LPCStates.IOADDR):
                m.d.sync += cyclecount.eq(cyclecount - 1)
                m.d.sync += addr.eq(Cat(self.lad_in, addr[:24]))
                # Make sure the read fifo is cleared out of any
                # entries before adding another. This could happen on
                # an LPC transaction abort (ie. when lframe/lreset is
                # asserted during a transaction).
                m.d.comb += self.rdcmd.en.eq(1)

                with m.If(cyclecount == 0):
                    m.d.sync += size.eq(0) # IO cycles are 1 byte
                    m.d.sync += cyclecount.eq(1)  # TAR 2 cycles
                    with m.If(cycletype == LPCCycletype.IORD):
                        m.d.comb += statenext.eq(LPCStates.RDTAR1)
                    with m.Elif(cycletype == LPCCycletype.IOWR):
                        m.d.comb += statenext.eq(LPCStates.WRDATA)
                    with m.Else():
                        m.d.comb += statenext.eq(LPCStates.START) # Bail

            with m.Case(LPCStates.FWIDSEL):
                # Respond to any IDSEL
                m.d.comb += statenext.eq(LPCStates.FWADDR)
                m.d.sync += cyclecount.eq(6) # 7 cycle FW addr

            with m.Case(LPCStates.FWADDR):
                m.d.comb += statenext.eq(LPCStates.FWADDR)
                m.d.sync += addr.eq(Cat(self.lad_in, addr[:24]))
                # Make sure the read fifo is cleared out of any
                # entries before adding another. This could happen on
                # an LPC transaction abort (ie. when lframe/lreset is
                # asserted during a transaction).
                m.d.comb += self.rdcmd.en.eq(1)

                m.d.sync += cyclecount.eq(cyclecount - 1)
                with m.If(cyclecount == 0):
                    m.d.comb += statenext.eq(LPCStates.FWMSIZE)

            with m.Case(LPCStates.FWMSIZE):
                with m.Switch(self.lad_in):
                    with m.Case(0b0000): # 1 byte
                        m.d.sync += size.eq(0)
                        m.d.sync += cyclecount.eq(1) # 1 byte = 2 nibbles
                    with m.Case(0b0001): # 2 bytes
                        m.d.sync += size.eq(1)
                        m.d.sync += cyclecount.eq(3) # 2 byte = 2 nibbles
                    with m.Case(0b0010): # 4 bytes
                        m.d.sync += size.eq(3)
                        m.d.sync += cyclecount.eq(7) # 4 byte = 8 nibbles
                    with m.Default():
                        m.d.comb += statenext.eq(LPCStates.START) # Bail

                with m.If(cycletype == LPCCycletype.FWRD):
                    m.d.sync += cyclecount.eq(1)  # TAR 2 cycles
                    m.d.comb += statenext.eq(LPCStates.RDTAR1)
                with m.Elif(cycletype == LPCCycletype.FWWR):
                    m.d.comb += statenext.eq(LPCStates.WRDATA)
                with m.Else():
                    m.d.comb += statenext.eq(LPCStates.START) # Bail

            # LPC FW and IO reads
            with m.Case(LPCStates.RDTAR1):
                # send off the command to the fifo in the first cycle
                m.d.comb += self.wrcmd.en.eq(cyclecount == 1)
                with m.If(cycletype == LPCCycletype.IORD):
                    m.d.comb += self.wrcmd.cmd.eq(LPCCycletype.IORD)
                with m.Else():
                    m.d.comb += self.wrcmd.cmd.eq(LPCCycletype.FWRD)

                m.d.sync += cyclecount.eq(cyclecount - 1)
                with m.If(cyclecount == 0):
                    m.d.comb += statenext.eq(LPCStates.RDSYNC)

            with m.Case(LPCStates.RDSYNC):
                m.d.comb += self.lad_out.eq(LPCSyncType.LONG_WAIT)
                m.d.comb += self.lad_en.eq(1)

                with m.If(self.rdcmd.rdy):
                    m.d.comb += self.rdcmd.en.eq(1)
                    m.d.comb += statenext.eq(LPCStates.RDDATA)
                    m.d.comb += self.lad_out.eq(LPCSyncType.READY)  # Ready

                    with m.Switch(size):
                        with m.Case(0): # 1 byte
                            m.d.sync += cyclecount.eq(1) # 1 byte = 2 nibbles
                            m.d.sync += data.eq(Cat(self.rdcmd.data[0:8],0))
                        with m.Case(1): # 2 bytes
                            m.d.sync += cyclecount.eq(3) # 2 byte = 2 nibbles
                            m.d.sync += data.eq(Cat(self.rdcmd.data[0:16],0))
                        with m.Case(3): # 4 bytes
                            m.d.sync += cyclecount.eq(7) # 4 byte = 8 nibbles
                            m.d.sync += data.eq(self.rdcmd.data)  # grab the data
                        with m.Default():
                            m.d.comb += statenext.eq(LPCStates.START) # Bail
                    # we shouldn't get FW errors, but here for completeness
                    with m.If(self.rdcmd.error):
                        m.d.comb += statenext.eq(LPCStates.START)
                        m.d.comb += self.lad_out.eq(LPCSyncType.ERROR)


            with m.Case(LPCStates.RDDATA):
                m.d.comb += self.lad_en.eq(1)
                m.d.sync += data.eq(Cat(data[4:], data[:28]))
                m.d.comb += self.lad_out.eq(data[:4])

                m.d.sync += cyclecount.eq(cyclecount - 1)
                with m.If(cyclecount == 0):
                    m.d.comb += statenext.eq(LPCStates.TAR2)
                    m.d.sync += cyclecount.eq(1)  # TAR cycles = 2

            # LPC IO and FW writes
            with m.Case(LPCStates.WRDATA):
                with m.Switch(size):
                    with m.Case(0): # 1 byte
                        m.d.sync += data.eq(Cat(data[4:8],self.lad_in))
                    with m.Case(1): # 2 bytes
                        m.d.sync += data.eq(Cat(data[4:16],self.lad_in))
                    with m.Case(3): # 4 bytes
                        m.d.sync += data.eq(Cat(data[4:32],self.lad_in))
                    with m.Default():
                        m.d.comb += statenext.eq(LPCStates.START) # Bail

                m.d.sync += cyclecount.eq(cyclecount - 1)
                with m.If(cyclecount == 0):
                    m.d.sync += cyclecount.eq(1)  # 2 cycle tar
                    m.d.comb += statenext.eq(LPCStates.WRTAR1)

            with m.Case(LPCStates.WRTAR1):
                # send off the command to the fifo in the first cycle
                m.d.comb += self.wrcmd.en.eq(cyclecount == 1)
                with m.If(cycletype == LPCCycletype.IOWR):
                    m.d.comb += self.wrcmd.cmd.eq(LPCCycletype.IOWR)
                with m.Else():
                    m.d.comb += self.wrcmd.cmd.eq(LPCCycletype.FWWR)

                m.d.sync += cyclecount.eq(cyclecount - 1)
                with m.If(cyclecount == 0):
                    m.d.comb += statenext.eq(LPCStates.WRSYNC)

            with m.Case(LPCStates.WRSYNC):
                m.d.comb += self.lad_out.eq(LPCSyncType.LONG_WAIT)
                m.d.comb += self.lad_en.eq(1)

                with m.If(self.rdcmd.rdy):  # wait for ack
                    m.d.comb += self.rdcmd.en.eq(1)
                    m.d.comb += statenext.eq(LPCStates.TAR2)
                    m.d.comb += self.lad_out.eq(LPCSyncType.READY)
                    m.d.sync += cyclecount.eq(1)  # 2 cycle tar
                    # we shouldn't get FW errors, but here for completeness
                    with m.If(self.rdcmd.error):
                        m.d.comb += statenext.eq(LPCStates.START)
                        m.d.comb += self.lad_out.eq(LPCSyncType.ERROR)

            with m.Case(LPCStates.TAR2):
                m.d.comb += self.lad_en.eq(1)
                m.d.comb += self.lad_out.eq(0b1111)

                m.d.sync += cyclecount.eq(cyclecount - 1)
                with m.If(cyclecount == 0):
                    m.d.comb += self.lad_en.eq(0)
                    m.d.comb += statenext.eq(LPCStates.START)  # Done

            with m.Default():
                m.d.comb += statenext.eq(LPCStates.START) # Bail

        # reset override
        with m.If(self.lreset == 0):
            m.d.comb += statenext.eq(LPCStates.START)
            m.d.comb += self.lad_en.eq(0) # override us driving
        # Start cycle can happen anywhere
        with m.If(self.lframe == 0):
            m.d.comb += self.wrcmd.rst.eq(1)
            m.d.comb += self.rdcmd.rst.eq(1)
            m.d.comb += self.lad_en.eq(0) # override us driving
            with m.Switch(self.lad_in):
                with m.Case(LPCStartType.MEMIODMA):
                    m.d.comb += statenext.eq(LPCStates.CYCLETYPE)
                with m.Case(LPCStartType.FWRD):
                    m.d.comb += statenext.eq(LPCStates.FWIDSEL)
                    m.d.sync += cycletype.eq(LPCCycletype.FWRD)
                with m.Case(LPCStartType.FWWR):
                    m.d.comb += statenext.eq(LPCStates.FWIDSEL)
                    m.d.sync += cycletype.eq(LPCCycletype.FWWR)
                with m.Default():
                    m.d.comb += statenext.eq(LPCStates.START) # Bail

        # fifo reset needs to be held for two cycles
        m.d.sync += lframesync.eq(self.lframe)
        m.d.comb += self.wrcmd.rst.eq(0)
        m.d.comb += self.rdcmd.rst.eq(0)
        with m.If((self.lframe == 0) | (lframesync == 0)):
            m.d.comb += self.wrcmd.rst.eq(1)
            m.d.comb += self.rdcmd.rst.eq(1)

        # Synthetic tristate LAD for looking at in Simulation. Can be removed.
        with m.If(self.lad_en):
            m.d.comb += self.lad_tri.eq(self.lad_out)
        with m.Else():
            m.d.comb += self.lad_tri.eq(self.lad_in)

        return m


if __name__ == "__main__":
    top = lpcfront()
    with open("lpcfront.v", "w") as f:
        f.write(verilog.convert(top))
