#!/usr/bin/env python
import sys
import os

import jinja2
import yaml


def jinja2_templater(yaml_file):
    """
    Generates a new file by filling in a j2 template.
    """
    with open(yaml_file) as f:
        data = yaml.load(f)

    config = data['parameters']
    vlnv = data['vlnv']
    files_root = data['files_root']

    template_filename = os.path.join(files_root, config['template_file'])
    template_parameters = config['template_parameters']
    output_filename = config['output_file']

    with open(template_filename, 'r') as f:
        template_text = f.read()
        template = jinja2.Template(template_text)
    formatted_text = template.render(**template_parameters)
    with open(output_filename, 'w') as f:
        f.write(formatted_text)

    # Edalize decide core_file dir. generator creates file.
    core_file = vlnv.split(':')[2]+'.core'

    coredata = {
        'name': vlnv,
        'targets': {'default': {'filesets': ['rtl'],}},
        'filesets': {'rtl': {'files': [output_filename]}},
        }

    with open(core_file, 'w') as f:
        f.write('CAPI=2:\n')
        f.write(yaml.dump(coredata))

    rc = 0
    return rc


if __name__ == '__main__':
    yaml_file = sys.argv[1]
    rc = jinja2_templater(yaml_file)
    exit(rc)
