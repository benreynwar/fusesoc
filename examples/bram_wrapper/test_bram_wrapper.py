import os
import random
import math

from verilate import verilator_cython, verilator_utils


def bram_wrapper_testbench(width, depth):
    memory = [None] * depth
    outputs = yield {
        'reset': 1,
        }
    last_cycle = None
    cycles = []
    for i in range(depth*5):
        address = random.randint(0, depth-1)
        data = random.randint(0, pow(2, width)-1)
        this_cycle = yield {
            'reset': 0,
            'w_valid': random.randint(0, 1),
            'w_address': random.randint(0, depth-1),
            'w_data': random.randint(0, pow(2, width)-1),
            'ar_valid': random.randint(0, 1),
            'ar_address': random.randint(0, depth-1),
            }
        if last_cycle is not None:
            assert this_cycle['r_valid'] == last_cycle['ar_valid']
            if this_cycle['r_valid']:
                expected = memory[last_cycle['ar_address']]
                if expected is not None:
                    assert this_cycle['r_data'] == expected
            else:
                assert this_cycle['r_data'] == last_cycle['r_data']
        if this_cycle['w_valid']:
            memory[this_cycle['w_address']] = this_cycle['w_data']
        cycles.append(this_cycle)
        last_cycle = this_cycle


def test():
    width = 3
    depth = 4
    filename = 'bram_wrapper_sim.sv'
    in_ports = [
        ('clk', 1),
        ('reset', 1),
        ('w_valid', 1),
        ('w_data', width),
        ('w_address', logceil(depth)),
        ('ar_valid', 1),
        ('ar_address', logceil(depth)),
        ]
    out_ports = [
        ('r_valid', 1),
        ('r_data', width),
        ]
    generics = {
        'WIDTH': width,
        'DEPTH': depth,
        }
    working_directory = 'working_verilate'
    os.makedirs(working_directory)
    verilator_cython.verilog_to_python(
        model_name='bram_wrapper',
        filenames=['bram_wrapper_sim.sv'],
        in_ports=in_ports,
        out_ports=out_ports,
        generics=generics,
        working_directory=working_directory,
    )
    import Vbram_wrapper
    Vbram_wrapper.XTraceEverOn()
    wrapped = Vbram_wrapper.Wrapped()
    tb = bram_wrapper_testbench(width, depth)
    verilator_utils.run_basic_test_with_verilator(wrapped, tb)

def logceil(v):
    return int(math.ceil(math.log(v)/math.log(2)))


if __name__ == '__main__':
    random.seed(0)
    test()
