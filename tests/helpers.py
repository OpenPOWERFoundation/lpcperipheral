import unittest

START_IO   = 0b0000
START_FWRD = 0b1101
START_FWWR = 0b1110

CYCLE_IOWRITE = 0b0010
CYCLE_IOREAD  = 0b0000

SYNC_READY      = 0b0000
SYNC_SHORT_WAIT = 0b0101
SYNC_LONG_WAIT  = 0b0110

class Helpers:
    def wishbone_write(self, wb, addr, data, sel=1, delay=1):
        yield wb.adr.eq(addr)
        yield wb.dat_w.eq(data)
        yield wb.we.eq(1)
        yield wb.cyc.eq(1)
        yield wb.stb.eq(1)
        yield wb.sel.eq(sel)

        # clock
        yield

        for i in range(delay):
            # clock
            yield

        self.assertEqual((yield wb.ack), 1)
        yield wb.we.eq(0)
        yield wb.cyc.eq(0)
        yield wb.stb.eq(0)
        yield wb.sel.eq(0)
        # Shouldn't need to clear dat and adr, so leave them set

    def wishbone_read(self, wb, addr, expected, sel=1, delay=1):
        yield wb.adr.eq(addr)
        yield wb.cyc.eq(1)
        yield wb.stb.eq(1)
        yield wb.we.eq(0)
        yield wb.sel.eq(sel)

        # clock
        yield

        for i in range(delay):
            # clock
            yield

        self.assertEqual((yield wb.ack), 1)
        self.assertEqual((yield wb.dat_r), expected)
        yield wb.cyc.eq(0)
        yield wb.stb.eq(0)
        yield wb.sel.eq(0)
        # Shouldn't need to clear dat and adr, so leave it

    # Partial transaction. Useful to test reset cases
    def lpc_io_read_partial(self, lpc, cycles):
        # Once driven things should start moving
        yield lpc.lframe.eq(0)
        yield lpc.lad_in.eq(START_IO)
        yield

        yield lpc.lframe.eq(1)
        yield lpc.lad_in.eq(CYCLE_IOREAD)

        for _ in range(cycles):
            yield

    def lpc_io_write(self, lpc, addr, data):
        # Once driven things should start moving
        yield lpc.lframe.eq(0)
        yield lpc.lad_in.eq(START_IO)
        yield

        yield lpc.lframe.eq(0)
        yield lpc.lad_in.eq(START_IO)
        yield

        yield lpc.lframe.eq(1)
        yield lpc.lad_in.eq(CYCLE_IOWRITE)
        yield

        # 16 bits of addr, little endian, least significant nibble first
        for i in reversed(range(0, 16, 4)):
            x = (addr >> i) & 0xf
            yield lpc.lad_in.eq(x)
            yield

        # 8 bits of data, big endian, most significant nibble first
        for i in range(0, 8, 4):
            x = (data >> i) & 0xf
            yield lpc.lad_in.eq(x)
            yield

        # TAR1 2 cycles
        yield lpc.lad_in.eq(0x1) # eyecatcher
        yield
        self.assertEqual((yield lpc.lad_en), 0)
        yield lpc.lad_in.eq(0x2) # eyecatcher
        yield
        self.assertEqual((yield lpc.lad_en), 0)

        # Sync cycles
        yield
        while (yield lpc.lad_out) == SYNC_LONG_WAIT:
            lad = yield lpc.lad_out
            # print("Write SYNC wait: LAD:0x%x" % (lad))
            self.assertEqual((yield lpc.lad_en), 1)
            yield
        self.assertEqual((yield lpc.lad_en), 1)
        self.assertEqual((yield lpc.lad_out), SYNC_READY)

        # TAR2 2 cycles
        yield
        self.assertEqual((yield lpc.lad_out), 0b1111)
        self.assertEqual((yield lpc.lad_en), 1)
        yield lpc.lad_in.eq(0xa) # eyecatcher
        yield
        self.assertEqual((yield lpc.lad_en), 0)

    def lpc_io_read(self, lpc, addr, data):
        # Once driven things should start moving
        yield lpc.lframe.eq(0)
        yield lpc.lad_in.eq(START_IO)
        yield

        yield lpc.lframe.eq(1)
        yield lpc.lad_in.eq(CYCLE_IOREAD)
        yield

        # 16 bits of addr, little endian, least significant nibble first
        for i in reversed(range(0, 16, 4)):
            x = (addr >> i) & 0xf
            yield lpc.lad_in.eq(x)
            yield

        # TAR1 2 cycles
        yield lpc.lad_in.eq(0x1) # eyecatcher
        yield
        self.assertEqual((yield lpc.lad_en), 0)
        yield lpc.lad_in.eq(0x2) # eyecatcher
        yield
        self.assertEqual((yield lpc.lad_en), 0)

        # Sync cycles
        yield
        while (yield lpc.lad_out) == SYNC_LONG_WAIT:
            lad = yield lpc.lad_out
            # print("Read SYNC wait: LAD:0x%x" % (lad))
            self.assertEqual((yield lpc.lad_en), 1)
            yield
        self.assertEqual((yield lpc.lad_en), 1)
        self.assertEqual((yield lpc.lad_out), SYNC_READY)

        # 8 bits of data, big endian, most significant nibble first
        for i in range(0, 8, 4):
            yield
            x = (data >> i) & 0xf
            self.assertEqual((yield lpc.lad_out), x)
            self.assertEqual((yield lpc.lad_en), 1)

        # TAR2 2 cycles
        yield
        self.assertEqual((yield lpc.lad_en), 1)
        self.assertEqual((yield lpc.lad_out), 0b1111)
        yield lpc.lad_in.eq(0xa) # eyecatcher
        yield
        self.assertEqual((yield lpc.lad_en), 0)

    def lpc_fw_write(self, lpc, addr, data, size):
        assert ((size == 4) | (size == 2) | (size == 1))
        # Once driven things should start moving
        yield lpc.lframe.eq(0)
        yield lpc.lad_in.eq(START_FWWR)
        yield

        yield lpc.lframe.eq(1)
        yield lpc.lad_in.eq(0) # IDSEL
        yield

        # 28 bits of addr, little endian, least significant nibble first
        for i in reversed(range(0, 28, 4)):
            x = (addr >> i) & 0xf
            yield lpc.lad_in.eq(x)
            yield

        # msize encoding. size is in byte
        if (size == 1):
            yield lpc.lad_in.eq(0b0000)
        elif (size == 2):
            yield lpc.lad_in.eq(0b0001)
        elif (size == 4):
            yield lpc.lad_in.eq(0b0010)
        else:
            assert(0)
        yield

        # 8 bits of data, big endian, most significant nibble first
        for i in range(0, size*8, 4):
            x = (data >> i) & 0xf
            yield lpc.lad_in.eq(x)
            yield

        # TAR1 2 cycles
        yield lpc.lad_in.eq(0x1) # eyecatcher
        yield
        self.assertEqual((yield lpc.lad_en), 0)
        yield lpc.lad_in.eq(0x2) # eyecatcher
        yield
        self.assertEqual((yield lpc.lad_en), 0)

        # Sync cycles
        yield
        while (yield lpc.lad_out) == SYNC_LONG_WAIT:
            lad = yield lpc.lad_out
            # print("Write SYNC wait: LAD:0x%x" % (lad))
            self.assertEqual((yield lpc.lad_en), 1)
            yield
        self.assertEqual((yield lpc.lad_en), 1)
        self.assertEqual((yield lpc.lad_out), SYNC_READY)

        # TAR2 2 cycles
        yield
        self.assertEqual((yield lpc.lad_en), 1)
        self.assertEqual((yield lpc.lad_out), 0b1111)
        yield lpc.lad_in.eq(0xa) # eyecatcher
        yield
        self.assertEqual((yield lpc.lad_en), 0)

    def lpc_fw_read(self, lpc, addr, data, size):
        assert ((size == 4) | (size == 2) | (size == 1))
        # Once driven things should start moving
        yield lpc.lframe.eq(0)
        yield lpc.lad_in.eq(START_FWRD)
        yield

        yield lpc.lframe.eq(1)
        yield lpc.lad_in.eq(0) # IDSEL
        yield

        # 28 bits of addr, little endian, least significant nibble first
        for i in reversed(range(0, 28, 4)):
            x = (addr >> i) & 0xf
            yield lpc.lad_in.eq(x)
            yield

        # msize encoding. size is in byte
        if (size == 1):
            yield lpc.lad_in.eq(0b0000)
        elif (size == 2):
            yield lpc.lad_in.eq(0b0001)
        elif (size == 4):
            yield lpc.lad_in.eq(0b0010)
        else:
            assert(0)
        yield

        # TAR1 2 cycles
        yield lpc.lad_in.eq(0x1) # eyecatcher
        yield
        self.assertEqual((yield lpc.lad_en), 0)
        yield lpc.lad_in.eq(0x2) # eyecatcher
        yield
        self.assertEqual((yield lpc.lad_en), 0)

        # Sync cycles
        yield
        while (yield lpc.lad_out) == SYNC_LONG_WAIT:
            lad = yield lpc.lad_out
            # print("Read SYNC wait: LAD:0x%x" % (lad))
            self.assertEqual((yield lpc.lad_en), 1)
            yield
        self.assertEqual((yield lpc.lad_en), 1)
        self.assertEqual((yield lpc.lad_out), SYNC_READY)

        # 32 bits of data, big endian, most significant nibble first
        for i in range(0, size*8, 4):
            yield
            x = (data >> i) & 0xf
            self.assertEqual((yield lpc.lad_out), x)
            self.assertEqual((yield lpc.lad_en), 1)

        # TAR2 2 cycles
        yield
        self.assertEqual((yield lpc.lad_out), 0b1111)
        self.assertEqual((yield lpc.lad_en), 1)
        yield lpc.lad_in.eq(0xa) # eyecatcher
        yield
        self.assertEqual((yield lpc.lad_en), 0)
