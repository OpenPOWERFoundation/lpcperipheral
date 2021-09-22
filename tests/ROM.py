import math
from nmigen import Elaboratable, Module, Memory
from nmigen_soc.wishbone import Interface
from nmigen.back import verilog


class ROM(Elaboratable, Interface):
    def __init__(self, data, data_width=32):
        self.data = data
        self.size = len(data)
        self.data_width = data_width

        # Initialize wishbone interface
        addr_width = math.ceil(math.log2(self.size + 1))
        super().__init__(data_width=data_width, addr_width=addr_width)

    def elaborate(self, platform):
        m = Module()

        data = Memory(width=self.data_width, depth=self.size, init=self.data)
        read_port = data.read_port()

        m.submodules.data = read_port

        m.d.comb += [
            read_port.addr.eq(self.adr),
            self.dat_r.eq(read_port.data),
        ]

        # Ack cycle after cyc and stb are asserted
        m.d.sync += self.ack.eq(self.cyc & self.stb)

        return m


if __name__ == "__main__":
    data = [0x11111111, 0x22222222, 0x33333333, 0x44444444]
    top = ROM(data=data)
    with open("ROM.v", "w") as f:
        f.write(verilog.convert(top))
