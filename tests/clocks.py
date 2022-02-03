#!/usr/bin/env python

# This is a little test program so I could work out how multiple clock
# domains work. Not really part of this project but a handy refrence

from amaranth import *
from enum import Enum, unique

class clocks(Elaboratable):

    def __init__(self):

        # LPC clock pin
        self.lclk  = Signal()
        self.counter = Signal(8)
        self.lcounter = Signal(8)

    def elaborate(self, platform):
        m = Module()

        lclk = ClockDomain("lclk")

        # hook up lclk port to lclk_domain
        m.d.comb += self.lclk.eq(ClockSignal("lclk"))

        m.d.sync += self.counter.eq(self.counter + 1)
        m.d["lclk"] += self.lcounter.eq(self.lcounter + 1)

        return m

# --- TEST ---
from amaranth.sim import Simulator


dut = clocks()
def bench():
    for _ in range(10):
        yield

def lbench():
    for _ in range(10):
        yield

sim = Simulator(dut)
sim.add_clock(1e-8) # 100 MHz systemclock
sim.add_clock(3e-8, domain="lclk") # 33 MHz LPC clock
sim.add_sync_process(bench, domain="sync")
sim.add_sync_process(lbench, domain="lclk")

with sim.write_vcd("clocks.vcd"):
    sim.run()

