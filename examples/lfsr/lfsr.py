import math
import argparse
import os

import yaml

import nmigen
from nmigen import Module, Signal, Mux, Instance, ClockSignal, ResetSignal
from nmigen.back import verilog

from fusesoc import main as fusesoc_main

import logging


logger = logging.getLogger(__name__)


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

    def __init__(self, width, tap0, tap1, fabric='XILINX'):
        # Parameters
        self.width = width
        self.tap0 = tap0
        self.tap1 = tap1
        self.fabric = fabric
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
            #p_FABRIC=self.fabric,
            p_DEPTH_CUTOFF=8,
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
            #p_FABRIC=self.fabric,
            p_DEPTH_CUTOFF=8,
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


def generate(parameters):
    params = parameters['parameters']
    output_directory = os.get_pwd()
    m = LFSR(width=params['width'], tap0=params['tap0'], tap1=params['tap1'])
    fragment = nmigen.Fragment.get(m, platform=None)
    output = verilog.convert(fragment, name='lfsr', ports=m.input_ports+m.output_ports)
    output_filename = os.path.join(output_directory, 'lfsr.v')
    with open(output_filename, 'w') as handle:
        handle.write(output)
    output_core_file = os.path.join(output_directory, 'lfsr.core')

    filesets = {
        'default': {'lfsr.v': {'filetype': 'vhdlSource'}},
        }
    targets = {
        'default': {'filesets': ['default']},
        }

    with open(output_core_file, 'w') as f:
        f.write('CAPI=2:\n')
        coredata = {
            'name': parameters['vlnv'],
            'filesets': filesets,
            'parameters': params,
            'targets': targets,
        }
        f.write(yaml.dump(coredata))

    return {'filenames': [output_filename]}


def configure_children(parameters):
    logger.warning('LFSR: Configuring children')
    m = LFSR(width=parameters['width'], tap0=parameters['tap0'],
             tap1=parameters['tap1']).elaborate(platform=None)
    child_input_parameters = {'shift_register': []}
    for submodule, submodule_name in m._submodules:
        assert submodule.type == 'shift_register'
        child_input_parameters['shift_register'].append(dict(submodule.parameters))
    output = {
        'child_input_parameters': child_input_parameters,
    }
    return output


def configure_parent(parameters):
    return {}


def check_parameters(parameters):
    expected = {
        'width': int,
        'tap0': int,
        'tap1': int,
        'fabric': str,
        }
    for name, typ in expected.items():
        if name not in parameters:
            raise RuntimeError('Parameters "{}" not found in call to lfsr generator'.format(name))
        if type(parameters[name]) != typ:
            raise RuntimeError('Parameter "{}" should have type {}. Found type {}.'.format(
                name, typ, type(parameters[name])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--configure', dest='configure_children', action='store_true')
    parser.add_argument('--configure-parent', dest='configure_parent', action='store_true')
    parser.add_argument('input_filename', type=str)
    parser.add_argument('output_filename', type=str, default=None, nargs='?')

    args = parser.parse_args()

    fusesoc_main.setup_logging(level=logging.DEBUG, monochrome=True, log_file=None)

    if args.configure_children and args.configure_parent:
        raise RuntimeError('Cannot configure both children and parents.')
    with open(args.input_filename, 'r') as f:
        parameters = yaml.safe_load(f.read())
    logger.warning('{}'.format(parameters))
    if not args.configure_children and not args.configure_parent:
        check_parameters(parameters['parameters'])
        output_parameters = generate(parameters)
    elif args.configure_children:
        check_parameters(parameters)
        output_parameters = configure_children(parameters)
        with open(args.output_filename, 'w') as f:
            f.write(yaml.dump(output_parameters))
    elif args.configure_parent:
        check_parameters(parameters)
        output_parameters = configure_parent(parameters)
        with open(args.output_filename, 'w') as f:
            f.write(yaml.dump(output_parameters))
