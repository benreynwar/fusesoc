import sys

import yaml

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


def generate_wrapper(all_parameters, fabric, language):
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
        if fabric == 'xilinx':
            filenames.append(generate_xilinx_bram(
                name=name, width=width, depth=depth, output_directory=output_directory))
        else:
            raise Exception(
                'Unknown fabric ({}). Only xilinx is currently supported').format(fabric)
        if language == 'vhdl':
            for_vhdl_wrapper.append({'width': width, 'depth': depth, 'name': name})
        elif language == 'verilog':
            for_verilog_wrapper.append({'width': width, 'depth': depth, 'name': name})
        else:
            assert language is None
    if for_vhdl_parameters:
        filenames.append(generate_wrapper(for_vhdl_wrapper, fabric, 'vhdl'))
    if for_verilog_parameters:
        filenames.append(generate_wrapper(for_verilog_wrapper, fabric, 'verilog'))
    return filenames


if __name__ == '__main__':
    parameters_filename = sys.argv[1]
    core_filename = sys.argv[2]
    with open(parameters_filename, 'r') as handle:
        parameters = yaml.load(handle.read())
    filenames = generate(parameters)
    content = make_core_from_filenames(
        filenames=filenames,
        core_name='bram_wrapper_generator',
        )
    with open(core_filename, 'w') as handle:
        handle.write(yaml.dump(content))
