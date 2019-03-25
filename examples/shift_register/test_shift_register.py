import os
import random
import math

from verilate import verilator_cython, verilator_utils

def shift_register_testbench_full_throughput(width, depth, target, depth_cutoff):
    outputs = yield {
        'reset': 1,
        }
    last_cycle = None
    data = []
    n_data = 100
    for i in range(n_data):
        outputs = yield {
            'reset': 0,
            'i_valid': 1,
            'i_data': random.randint(0, pow(2, width)-1),
            }
        data.append(outputs)
    in_valids = [d['i_valid'] for d in data]
    out_valids = [d['o_valid'] for d in data]
    if depth > 0:
        assert in_valids[:-depth] == out_valids[depth:]
    else:
        assert in_valids == out_valids
    in_data = [d['i_data'] for d in data]
    out_data = [d['o_data'] for d in data]
    if depth > 0:
        assert in_data[:-depth] == out_data[depth:]
    else:
        assert in_data == out_data


def shift_register_testbench_stuttered(width, depth, target, depth_cutoff):
    outputs = yield {
        'reset': 1,
        }
    last_cycle = None
    data = []
    n_data = 100
    
    for i in range(n_data):
        outputs = yield {
            'reset': 0,
            'i_valid': random.randint(0, 1),
            'i_data': random.randint(0, pow(2, width)-1),
            }
        data.append(outputs)
    for i in range(depth):
        outputs = yield {
            'reset': 0,
            'i_valid': 1,
            'i_data': random.randint(0, pow(2, width)-1),
            }
        data.append(outputs)
    in_data = [d['i_data'] for d in data if d['i_valid']]
    if depth > 0:
        in_data = in_data[:-depth]
    out_data = [d['o_data'] for d in data if d['o_valid']]
    assert in_data == out_data


def combine_tests(*tests):
    for test in tests:
        yield from test


def test():
    width = 3
    depth = 4
    target = '"XILINX"'
    depth_cutoff = 2
    filenames = ['shift_register.sv', '../bram_wrapper/bram_wrapper_sim.sv']
    in_ports = [
        ('clk', 1),
        ('reset', 1),
        ('i_valid', 1),
        ('i_data', width),
        ]
    out_ports = [
        ('o_valid', 1),
        ('o_data', width),
        ]
    generics = {
        'WIDTH': width,
        'DEPTH': depth,
        'TARGET': target,
        'DEPTH_CUTOFF': depth_cutoff,
        }
    working_directory = 'working_verilate'
    os.makedirs(working_directory)
    verilator_cython.verilog_to_python(
        'shift_register', filenames, in_ports, out_ports, generics, working_directory)
    import Vshift_register
    Vshift_register.XTraceEverOn()
    wrapped = Vshift_register.Wrapped(**generics)
    tb = combine_tests(
        shift_register_testbench_full_throughput(width, depth, target, depth_cutoff),
        shift_register_testbench_stuttered(width, depth, target, depth_cutoff),
        )
    verilator_utils.run_basic_test_with_verilator(wrapped, tb)


if __name__ == '__main__':
    random.seed(0)
    test()
