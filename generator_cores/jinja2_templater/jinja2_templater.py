#!/usr/bin/env python
import sys
import yaml
import jinja2


def jinja2_templater(yaml_file):
    """
    Generates a new file by filling in a j2 template.
    """
    with open(sys.argv[1]) as f:
        data = yaml.load(f)

    config = data['parameters']
    vlnv = data['vlnv']

    template_filename = config['template_file']
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
        'targets': {'default': {'filesets': ['rtl'],
                                'parameters': template_parameters.keys()}},
        'filesets': {'rtl': {'files': [output_filename]}},
        'parameters': template_parameters,
        }

    with open(core_file, 'w') as f:
        f.write('CAPI=2:\n')
        f.write(yaml.dump(coredata))
    return rc


if __name__ == '__main__':
    yaml_file = sys.argv[1]
    rc = jinja2_templater(yaml_file)
    exit(rc)
