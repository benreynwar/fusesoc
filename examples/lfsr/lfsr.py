import math

import nmigen
from nmigen import Module, Signal, Mux, Instance, ClockSignal, ResetSignal
from nmigen.back import verilog


def logceil(argument):
    if argument < 2:
        value = 0
    else:
        value = int(math.ceil(math.log(argument)/math.log(2)))
    return value


def lfsr_model(tap0, tap1, seed):
    assert len(seed) == tap1
    state = [x for x in seed]
    while True:
        output = state[-tap1] ^ state[-tap0]
        state.pop(0)
        state.append(output)
        yield output


class LFSR:

    def __init__(self, width, tap0, tap1, target='XILINX'):
        # Parameters
        self.width = width
        self.tap0 = tap0
        self.tap1 = tap1
        self.target = target
        # Ports
        self.seed_valid = Signal()
        self.seed_data = Signal(width)
        self.o_valid = Signal()
        self.o_data = Signal(width)
        self.input_ports = [
            self.seed_valid,
            self.seed_data,
            ]
        self.output_ports = [
            self.o_valid,
            self.o_data,
            ]

    def elaborate(self, platform):
        m = Module()

        # Create a counter that sets 'is_running' to 1 after
        # `self.tap1` seeds have been received.
        counter = Signal(max=self.tap1, reset=0)
        is_running = Signal(reset=0)
        with m.If(self.seed_valid == 1):
            m.d.sync += counter.eq(counter + 1)
            with m.If(counter == self.tap1-1):
                m.d.sync += is_running.eq(1)

        tofirstpipe_valid = Signal()
        tofirstpipe_data = Signal(self.width)
        fromfirstpipe_valid = Signal(self.width+1)
        fromfirstpipe_data = Signal(self.width+1)
        m.d.comb += [
            tofirstpipe_valid.eq(self.seed_valid | is_running),
            tofirstpipe_data.eq(Mux(is_running, self.o_data, self.seed_data)),
            ]

        m.submodules.firstpipe = Instance(
            "shift_register",
            p_WIDTH=self.width,
            p_DEPTH=self.tap0,
            p_TARGET=self.target,
            p_DEPTH_CUTOFF=32,
            i_clk=ClockSignal(),
            i_reset=ResetSignal(),
            i_i_valid=tofirstpipe_valid,
            i_i_data=tofirstpipe_data,
            o_o_valid=fromfirstpipe_valid,
            o_o_data=fromfirstpipe_data,
            )

        fromsecondpipe_valid = Signal()
        fromsecondpipe_data = Signal(self.width)

        m.submodules.secondpipe = Instance(
            "shift_register",
            p_WIDTH=self.width,
            p_DEPTH=self.tap1-self.tap0,
            p_TARGET=self.target,
            p_DEPTH_CUTOFF=32,
            i_clk=ClockSignal(),
            i_reset=ResetSignal(),
            i_i_valid=fromfirstpipe_valid,
            i_i_data=fromfirstpipe_data,
            o_o_valid=fromsecondpipe_valid,
            o_o_data=fromsecondpipe_data,
            )

        m.d.comb += [
            self.o_valid.eq(is_running),
            self.o_data.eq(fromsecondpipe_data ^ fromfirstpipe_data),
            ]

        return m

def main():
    m = LFSR(width=32, tap0=31, tap1=50)
    #a = convert(m, m.ios)
    fragment = nmigen.Fragment.get(m, platform=None)
    output = verilog.convert(fragment, name='lfsr', ports=self.input_ports+self.output_ports)
    print(output)

if __name__ == '__main__':
    main()
