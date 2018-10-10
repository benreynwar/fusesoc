#!/usr/bin/env python
import sys

import yaml

TEMPLATE = """
create_ip -name {core_name} -vendor {vendor} -library {library} -version {version} -module_name {module_name}
set_property -dict [list {core_properties}] [get_ips {module_name}]
"""


def xilinx_core_generator(yaml_file):
    """
    Generates a new file to generate a xilinx ip core.
    TODO: Add at least 3 more layers of generation on top of one another.
    """
    with open(yaml_file) as f:
        data = yaml.load(f)

    config = data['parameters']
    vlnv = data['vlnv']
    output_files = config.get('output_files')
    assert len(output_files) == 1
    assert len(list(output_files[0].keys())) == 1
    output_tcl_script = list(output_files[0].keys())[0]
    assert output_tcl_script[-4:] == '.tcl'

    core_properties = config.get('core_parameters', {})
    core_properties_text = ' '.join(['CONFIG.{k} {{{v}}}'.format(k=k, v=v)
                                     for k, v in core_properties.items()])

    tcl_file_contents = TEMPLATE.format(
        core_name=config['core_name'],
        module_name=config['module_name'],
        version=config['version'],
        vendor=config.get('vendor', 'xilinx.com'),
        library=config.get('library', 'ip'),
        core_properties=core_properties_text,
        )
    print(core_properties)
    print(core_properties_text)
    print(tcl_file_contents)

    with open(output_tcl_script, 'w') as f:
        f.write(tcl_file_contents)

    # Edalize decide core_file dir. generator creates file.
    core_file = vlnv.split(':')[2]+'.core'

    coredata = {
        'name': vlnv,
        'targets': {'default': {'filesets': ['tcl'],}},
        'filesets': {'tcl': {'files': [output_tcl_script],
                             'file_type': 'tclSource'}},
        }

    with open(core_file, 'w') as f:
        f.write('CAPI=2:\n')
        f.write(yaml.dump(coredata))

    rc = 0
    return rc


if __name__ == '__main__':
    yaml_file = sys.argv[1]
    rc = xilinx_core_generator(yaml_file)
    exit(rc)
