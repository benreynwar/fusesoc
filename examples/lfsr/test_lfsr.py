import os
import random

import nmigen
from nmigen.back import verilog

from verilate import verilator_cython, verilator_utils

import lfsr

def lfsr_testbench(width, tap0, tap1):
    n_data = 100
    # Send seed
    yield {'rst': 1}
    outputs = []
    seeds_sent = 0
    while seeds_sent < tap1:
        output = yield {
            'rst': 0,
            'seed_valid': random.randint(0, 1),
            'seed_data': random.randint(0, pow(2, width)-1),
            }
        outputs.append(output)
        seeds_sent += output['seed_valid']
        #assert output['o_valid'] == 0
    for i in range(n_data):
        output = yield {
            'rst': 0,
            'seed_valid': 0,
            }
        outputs.append(output)
    seed = [d['seed_data'] for d in outputs if d['seed_valid']]
    received = [d['o_data'] for d in outputs if d['o_valid']]
    model = lfsr.lfsr_model(tap0, tap1, seed)
    expected = [next(model) for i in range(len(received))]
    assert received == expected
    

def test_lfsr():
    working_directory = 'working_verilate'
    os.makedirs(working_directory)

    width = 32
    tap0 = 31
    tap1 = 50
    m = lfsr.LFSR(width=32, tap0=31, tap1=50)
    fragment = nmigen.Fragment.get(m, platform=None)
    content = verilog.convert(fragment, name='lfsr', ports=m.input_ports + m.output_ports)
    lfsr_filename = os.path.join(working_directory, 'lfsr.v')
    with open(lfsr_filename, 'w') as handle:
        handle.write(content)

    filenames = [lfsr_filename, '../shift_register/shift_register.sv', '../bram_wrapper/bram_wrapper_sim.sv']
    in_ports = [(p.name, p.nbits) for p in m.input_ports] + [('clk', 1), ('rst', 1)]
    out_ports = [(p.name, p.nbits) for p in m.output_ports]
    generics = {}
    verilator_cython.verilog_to_python(
        'lfsr', filenames, in_ports, out_ports, generics, working_directory)
    import Vlfsr
    Vlfsr.XTraceEverOn()
    wrapped = Vlfsr.Wrapped(**generics)
    tb = lfsr_testbench(width, tap0, tap1)
    verilator_utils.run_basic_test_with_verilator(wrapped, tb, clock_name='clk')
    

if __name__ == '__main__':
    test_lfsr()
