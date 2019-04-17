import argparse
import os
import jinja2
import logging

import yaml

from fusesoc import main as fusesoc_main


logger = logging.getLogger(__name__)


THIS_DIRECTORY = os.path.dirname(os.path.realpath(__file__))


def generate_xilinx_bram(name, width, depth, output_directory):
    """
    Generates a TCL file that instantiates a xilinx bram.
    """
    template_filename = os.path.join(THIS_DIRECTORY, 'xilinx_bram_wrapper.tcl')
    with open(template_filename, 'r') as handle:
        template = jinja2.Template(handle.read())
    content = template.render(
        name=name,
        width=width,
        depth=depth,
        )
    output_filename = os.path.join(output_directory, 'bram_{}_{}.tcl'.format(width, depth))
    with open(output_filename, 'w') as handle:
        handle.write(content)
    return output_filename


def generate_wrapper(all_parameters, fabric, language, output_directory):
    """
    Generates a VHDL or verilog wrapper that instantiates the appropriate bram ip depending on the
    width and generic given as generics.
    """
    if language == 'vhdl':
        template_filename = os.path.join(THIS_DIRECTORY, 'bram_wrapper.vhd')
        output_filename = os.path.join(output_directory, 'bram_wrapper.vhd')
    elif language == 'verilog':
        template_filename = os.path.join(THIS_DIRECTORY, 'bram_wrapper.v')
        output_filename = os.path.join(output_directory, 'bram_wrapper.v')
    else:
        raise Exception('Unknown language {}'.format(language))
    with open(template_filename, 'r') as handle:
        template = jinja2.Template(handle.read())
    content = template.render(all_parameters=all_parameters, fabric=fabric)
    with open(output_filename, 'w') as handle:
        handle.write(content)
    return output_filename


def generate(all_parameters, output_directory):
    filenames = []
    for_vhdl_wrapper = []
    for_verilog_wrapper = []
    fabric = None
    for parameters in all_parameters:
        language = parameters.get('language', None)
        width = parameters['width']
        depth = parameters['depth']
        name = parameters.get('name', 'bram_{}_{}'.format(width, depth))
        if fabric is None:
            fabric = parameters['fabric']
        else:
            assert fabric == parameters['fabric']
        if fabric == 'XILINX':
            filenames.append(generate_xilinx_bram(
                name=name, width=width, depth=depth, output_directory=output_directory))
        else:
            raise Exception(
                'Unknown fabric ({}). Only XILINX is currently supported'.format(fabric))
        if language == 'vhdl':
            for_vhdl_wrapper.append({'width': width, 'depth': depth, 'name': name})
        elif language == 'verilog':
            for_verilog_wrapper.append({'width': width, 'depth': depth, 'name': name})
        else:
            assert language is None
    if for_vhdl_wrapper:
        filenames.append(generate_wrapper(for_vhdl_wrapper, fabric, 'vhdl', output_directory))
    if for_verilog_wrapper:
        filenames.append(generate_wrapper(for_verilog_wrapper, fabric, 'verilog', output_directory))
    return filenames


def configure_children(parameters):
    logger.warning('bram_wrapper: Running configure_children: {}'.format(parameters))
    return {}


def check_parameters(parameters, gathered):
    if 'parameters' not in parameters:
        raise RuntimeError('Missing "parameters" in call to bram_wrapper generator')
    if 'output_directory' not in parameters:
        print(parameters)
        raise RuntimeError('Missing "output_directory" in call to bram_wrapper generator')
    params = parameters['parameters']
    if not gathered:
        check_single_parameters(params)
    else:
        for p in params:
            check_single_parameters(p)


def check_single_parameters(params):
    expected = {
        'width': int,
        'depth': int,
        }
    for name, typ in expected.items():
        if name not in params:
            raise RuntimeError('Parameters "{}" not found in call to bram_wrapper generator'.format(name))
        if type(params[name]) != typ:
            raise RuntimeError('Parameter "{}" should have type {}. Found type {}.'.format(
                name, typ, type(params[name])))


def main():
    fusesoc_main.setup_logging(level=logging.DEBUG, monochrome=True, log_file=None)
    parser = argparse.ArgumentParser()
    parser.add_argument('--configure', dest='configure_children', action='store_const',
                        const=True, default=False)
    parser.add_argument('--configure-parent', dest='configure_parent', action='store_const',
                        const=True, default=False)
    parser.add_argument('input_filename', type=str)
    parser.add_argument('output_filename', type=str, default=None, nargs='?')
    args = parser.parse_args()
    logger.warning('Running bram wrapper')
    if args.configure_children and args.configure_parent:
        raise RuntimeError('Cannot configure both children and parents.')
    with open(args.input_filename, 'r') as f:
        parameters = yaml.safe_load(f.read())
    if not args.configure_children and not args.configure_parent:
        print(parameters)
        config = parameters['parameters']
        check_parameters(config, True)
        logger.warning('Running bram wrapper generate')
        output = generate(config['parameters'], config['output_directory'])
        #with open(args.output_filename, 'w') as f:
        #    parameters = f.write(yaml.dump({'filenames': output}))
    elif args.configure_children:
        check_parameters(parameters, False)
        logger.warning('Running bram wrapper configure')
        output_parameters = configure_children(parameters)
        with open(args.output_filename, 'w') as f:
            parameters = f.write(yaml.dump(output_parameters))
    elif args.configure_parent:
        check_parameters(parameters, False)
        logger.warning('Running bram wrapper configure-parent')
        output_parameters = {}
        with open(args.output_filename, 'w') as f:
            parameters = f.write(yaml.dump(output_parameters))


if __name__ == '__main__':
    main()
