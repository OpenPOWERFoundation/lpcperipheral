# LPC Peripheral Overview

This is an LPC peripheral that implements LPC IO and FW cycles so that
it can boot a host like a POWER9. This peripheral would typically sit
inside a BMC SoC.

It implements the Intel Low Pin Count (LPC) spec from
[here](https://www.intel.com/content/dam/www/program/design/us/en/documents/low-pin-count-interface-specification.pdf).

# System diagram
```
                              .
                              .
  LPC       LPC Clock         .       System Clock
  pins                        .                        LPC FW               DMA
        +---------+     +------------+     +--------+ Wishbone +--------+ Wishbone
        |         |     |   ASYNC    |     |        |          |  LPC   |  Master
  LCLK  |         +---->|  FIFO WR   +---->|        +--------->|  CTRL  +-------->
------->|   LPC   |     |            |     |        |          |        |
        |  Front  |     +------------+     | LOGIC  |          +--------+
 LFRAME |         |           .            |        |
------->|         |     +------------+     |        |          +--------+
        |         |     |   ASYNC    |     |        |          | IPMI BT|
  LAD   |         |<----+  FIFO RD   |<----+        +--------->|  FIFO  |<--------
<------>|         |     |            |     |        |          |        |   IO
        +---------+     +------------+     +--------+  LPC IO  +--------+ Wishbone
                              .                       Wishbone |  UART  |  Slave
                              .                                |        |
                              .                                +--------+
                              .                                |  CTRL  |
                                                               |        |
                                                               +--------+
```

The design translates the LPC IO accesses into a wishbone master. The
same is done for FW accesses.

The LPC IO wishbone master bus has devices attached to it. These
include a an IPMI BT FIFO and standard 16550 UART. The back end of
these can then be access by an external IO wishbone slave (which would
typically come from the BMC CPU).

The LPC FW wishbone master gets translated into an external wishbone
master. This translation provides an offset and mask so the external
wishbone master accesses occur can be controlled. Typically this
external wishbone will be hooked into a DMA path the system bus of the
BMC, so where this can access needs to be controlled.

The LPC front end runs using the LPC clock. The rest of the design
works on the normal system clock. Async FIFOs provide a safe boundary
between the two.

HDL is written in nmigen because that's what all the cool kids are
doing. This is our first nmigen project, and we are software
developers, so be kind!

# Building

This is designed to be integrated into some other project (like
microwatt for libreBMC) not build as a standalone project.

If you want the verilog, do this to produce a lpcperipheral.v
```
python -m lpcperipheral.lpcperipheral
```

# Testing

There are an extensive set of tests in tests/. To run these do:

```
python -m unittest
```
