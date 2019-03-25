import sys

import yaml


def configure(parameters):
    back_parameters = {}
    return back_parameters


if __name__ == '__main__':
    parameters_filename = sys.argv[1]
    back_parameters_filename = sys.argv[2]
    with open(parameters_filename, 'r') as handle:
        parameters = yaml.load(handle.read())
    configure(parameters)
    with open(back_parameters_filename, 'w') as handle:
        handle.write(yaml.dump(back_parameters))
