import os
import copy
import logging
import yaml
import glob
import json

import edalize
from edalize import edatool

from fusesoc.vlnv import Vlnv

logger = logging.getLogger(__name__)


def fusesoc_file_to_edalize_file(fusesoc_file):
    """
    Convert a fusesoc file object, into a dictionary suitable for
    writing into a configuration file for edalize.
    """
    return {
        'name': fusesoc_file.name,
        'file_type': fusesoc_file.file_type,
        'is_include_file': fusesoc_file.is_include_file,
        'logical_name': fusesoc_file.logical_name,
        }


def get_work_root(cache_root, core, fileset=None, generate=None, generator=None, configure=True):
    """
    Get the name of the working directory for configuration or generation.
    """
    if fileset is not None:
        assert generate is None
        assert generator is None
        item = fileset
        tag = 'fileset'
    elif generate is not None:
        item = generate
        assert generator is None
        tag = 'generate'
    else:
        item = generator
        assert generator is not None
        tag = 'generator'
    vlnv_str = ':'.join([core.name.vendor, core.name.library,
                         core.name.name + '-{}-'.format(tag) + item.name,
                         core.name.version])
    vlnv = Vlnv(vlnv_str)
    operation_label = 'configure' if configure else 'generate'
    working_dir = os.path.join(cache_root, operation_label, vlnv.sanitized_name)
    return working_dir


def files_from_fileset(core_root, fileset):
    """
    Convert a fileset object into a list of fusesoc files.
    Relative files are converted into absolute files.
    """
    files = []
    if fileset is not None:
        for f in fileset.files:
            new_f = copy.copy(f)
            if not os.path.isabs(new_f.name):
                new_f.name = os.path.join(core_root, new_f.name)
            files.append(new_f)
    return files


class BaseGenerator:

    def __init__(self, name, cache_root, core, generator):
        self.name = name
        self.core_name = core.name.name
        self.core = core
        # Whether the command executable produces configuration parameters for children
        self.configures_children_with_command = generator.configures_children_with_command
        # Whether the generated files must be simulated to extract the configuration parameters
        # for children.
        self.configures_children_with_fileset = (
            generator.configurable_from_vhdl or generator.configurable_from_verilog)
        assert not (self.configures_children_with_command and self.configures_children_with_fileset)
        # Whether the generator can return configuration parameters to it's parent.
        self.can_configure_parent = generator.can_configure_parent
        self.interpreter = generator.interpreter
        self.command = os.path.join(core.core_root, generator.command)
        self.work_root = get_work_root(
            cache_root, core, generator=generator)
        self.generator = generator

    def generate(self, parameters, files=None):
        if self.generated:
            return self.generate_output
        if not os.path.exists(self.work_root):
            os.makedirs(self.work_root)
        input_parameter_filename = os.path.join(self.work_root, 'generate_input.yaml')
        output_parameter_filename = os.path.join(self.work_root, 'generate_output.yaml')
        with open(input_parameter_filename, 'w') as handle:
            handle.write(yaml.dump({
                'parameters': parameters,
                'files': files,
                'output_directory': self.work_root,
            }))
        cmd = self.interpreter
        args = [self.command, input_parameter_filename, output_parameter_filename]
        stdout_fn = os.path.join(self.work_root, 'generate_stdout')
        stderr_fn = os.path.join(self.work_root, 'generate_stderr')
        edatool.call_and_capture_output(
            cmd, args, self.work_root, stdout_fn, stderr_fn,
            output_stdout=False, output_stderr=False,
            line_callback=edatool.standard_line_callback)
        with open(output_parameter_filename, 'r') as handle:
            output = yaml.safe_load(handle.read())
        self.generate_output = output
        self.generated = True
        return output


class SingleUseGenerator(BaseGenerator):
    """
    A generator that generates files, and can only be used with a single set
    of parameters in a design.
    """

    def __init__(self, name, cache_root, core, generator):
        super().__init__(name, cache_root, core, generator)
        self.parameters = None
        self.files = None
        self.generated = False
        self.always_configure = False

    def add_parameters(self, parameters):
        self.parameters = parameters

    def generate(self, parameters, files):
        if not self.generated:
            super().generate(parameters, files)
            self.parameters = parameters
            self.files = files
            self.generated = True
        else:
            assert parameters == self.parameters
            assert files == self.files


class MultipleUseGenerator(BaseGenerator):
    """
    A generator that runs separately for each set of parameters.
    """
    def __init__(self, name, cache_root, core, generator):
        super().__init__(name, cache_root, core, generator)
        self.parameters = None
        self.generated_parameters = {}
        self.always_configure = False

    def add_parameters(self, parameters):
        self.parameters = parameters

    def generate(self, name, parameters, files):
        if name in self.generated_parameters:
            assert parameters == self.generated_parameters[name]
        else:
            super().generate(parameters)
            self.generated_parameters[name] = parameters


class GatheringGenerator(BaseGenerator):
    """
    A gathering generator collects parameters from many generate sections
    and then runs a generation script that has access to all these parameters.
    """

    def __init__(self, name, cache_root, core, generator):
        super().__init__(name, cache_root, core, generator)
        self.parameters = []
        self.generated = False
        self.always_configure = True

    def add_parameters(self, parameters):
        self.parameters.append(parameters)

    def generate(self):
        assert not self.generated
        super().generate(self.parameters)
        self.generated = True


def make_generator(name, cache_root, core, generator):
    if generator.single_use:
        new_generator = SingleUseGenerator(name, cache_root, core, generator)
    elif generator.gathers_parameters:
        new_generator = GatheringGenerator(name, cache_root, core, generator)
    else:
        new_generator = MultipleUseGenerator(name, cache_root, core, generator)
    return new_generator


class FilesetNode:
    """
    A node in a dependency tree representing a set of files.
    Corresponds to a fileset in a core file.
    """

    def __init__(self, cache_root, core, fileset, toplevel, children, sim_filesets=None):
        self.name = core.name.name + '_' + fileset.name
        self.needs_configuring = False
        self.can_configure_parent = False
        self.configures_children_with_fileset = True
        self.configures_children_with_command = False
        self.children = children
        self.files = files_from_fileset(core.core_root, fileset)
        self.sim_files = []
        for sim_fileset in sim_filesets:
            self.sim_files += files_from_fileset(core.core_root, sim_fileset)
        self.toplevel = toplevel
        self.work_root = get_work_root(
            cache_root, core, fileset=fileset)

    def has_children_requiring_configuring(self):
        """
        Check if this node has any children that need to be configured.
        """
        for child in self.children:
            if child.needs_configuring or child.has_children_requiring_configuring():
                return True
        return False


class GenerateNode:
    """
    A node in a dependency representing a call to a generator.
    Corresponds to a 'generate' in a core file.
    """

    def __init__(self, cache_root, core, generate, generator_core, generator, children,
                 from_vhdl_fileset=None, from_verilog_fileset=None):
        self.name = core.name.name + '_' + generate.name
        self.generate = generate
        self.core_name = core.name.name
        self.core = core
        self.needs_configuring = generate.needs_configuring or generator.always_configure
        self.can_configure_parent = generator.generator.can_configure_parent
        self.interpreter = generator.generator.interpreter
        self.command = os.path.join(generator_core.core_root, generator.generator.command)
        self.children = children
        self.from_vhdl_fileset = from_vhdl_fileset
        self.from_verilog_fileset = from_verilog_fileset
        self.work_root = get_work_root(
            cache_root, core, generate=generate)
        self.generator = generator
        if not generate.parameters:
            self.base_parameters = {}
        else:
            self.base_parameters = generate.parameters
        self.parameters = []
        self.generate_output = None

    def has_children_requiring_configuring(self):
        """
        Check if this node has any children that need to be configured.
        """
        for child in self.children:
            if child.needs_configuring or child.has_children_requiring_configuring():
                return True
        return False

    def generate_before_configuring_children(self):
        return self.configure_children_with_fileset

    def configure_children(self, input_parameters):
        """
        Run configuration on this node followed by configuration on it's children.
        """
        # Run the configuration script.
        input_parameter_filename = os.path.join(self.work_root, 'configure_input.yaml')
        output_parameter_filename = os.path.join(self.work_root, 'configure_output.yaml')
        with open(input_parameter_filename, 'w') as handle:
            handle.write(yaml.dump({
                'parameters': input_parameters,
                'output_directory': self.work_root,
            }))
        cmd = self.interpreter
        args = [self.command, '--configure', input_parameter_filename, output_parameter_filename]
        stdout_fn = os.path.join(self.work_root, 'configure_stdout')
        stderr_fn = os.path.join(self.work_root, 'configure_stderr')
        edatool.call_and_capture_output(
            cmd, args, self.work_root, stdout_fn, stderr_fn,
            output_stdout=False, output_stderr=False,
            line_callback=edatool.standard_line_callback)
        with open(output_parameter_filename, 'r') as handle:
            output = yaml.safe_load(handle.read())
        # The output parameters from configuration contain parameters to pass to children
        # in 'child_input_parameters'.
        # If the children don't have unique names we can't tell which parameters go to
        # which.
        names = [child.name for child in self.children]
        assert len(names) == len(set(names))
        child_output_parameters = {}
        for child in self.children:
            child_input_parameters = output.get('child_input_parameters', {})
            for parameter_set in child_input_parameters.get(child.name, []):
                child_output_parameters[child.name] = child.configure(parameter_set)
        return child_output_parameters

    def configure_parent(self, input_parameters):
        """
        It is possible for child nodes to influence the parameters that the parent
        node will use for generation.
        This calls a executable that returns parameters to pass to the parent.
        """
        input_parameter_filename = os.path.join(self.work_root, 'configure_parent_input.yaml')
        output_parameter_filename = os.path.join(self.work_root, 'configure_parent_output.yaml')
        with open(input_parameter_filename, 'w') as handle:
            dumped = yaml.dump({
                'parameters': input_parameters,
                'output_directory': self.work_root,
            })
            assert '!!' not in dumped
            handle.write(dumped)
        stdout_fn = os.path.join(self.work_root, 'configure_parent_stdout')
        stderr_fn = os.path.join(self.work_root, 'configure_parent_stderr')
        args = [self.command, '--configure-parent', input_parameter_filename,
                output_parameter_filename]
        edatool.call_and_capture_output(
            self.interpreter, args, self.work_root, stdout_fn, stderr_fn,
            output_stdout=False, output_stderr=False,
            line_callback=edatool.standard_line_callback)
        if os.path.exists(output_parameter_filename):
            with open(output_parameter_filename, 'r') as handle:
                output_parameters = yaml.load(handle.read())
        else:
            output_parameters = {}
        return output_parameters

    def configure(self, input_parameters):
        """
        Run configuration on this node and it's children.
        Return configuration parameters to parent.
        """
        for name, value in self.base_parameters.items():
            assert name not in input_parameters
            input_parameters[name] = value
        if not os.path.exists(self.work_root):
            os.makedirs(self.work_root)
        if self.needs_configuring or self.has_children_requiring_configuring():
            logger.info('{} running configure children'.format(self.name))
            child_output_parameters = self.configure_children(input_parameters)
            input_parameters['child_output_parameters'] = child_output_parameters
            self.generator.add_parameters(input_parameters)
            logger.info('{} running configure parent'.format(self.name))
        if self.can_configure_parent:
            output_parameters = self.configure_parent(input_parameters)
            logger.info('{} done with configure'.format(self.name))
        else:
            output_parameters = {}
        return output_parameters

    def get_files_to_configure_from_fileset(self, language):
        """
        If a generator is to be configured from a fileset, then it must provide some files
        that can be compiled and simulated with that fileset, and which log the desired parameters
        to stdout.
        A generated can provide a vhdl and a verilog fileset so that it can be configured
        from either language.
        """
        assert language in ('vhdl', 'verilog')
        if language == 'vhdl':
            files = files_from_fileset(self.core.core_root, self.from_vhdl_fileset)
        elif language == 'verilog':
            files = files_from_fileset(self.core.core_root, self.from_verilog_fileset)
        return files

    def generate(self):
        """
        Generate and collect all the files necessary for this node and it's children.
        """
        all_filenames = []
        for child in self.children:
            all_filenames += child.generate()
        generator_output = self.generator.generate(all_filenames)
        all_filenames += generator_output['filenames']
        return all_filenames


class NeighborhoodNode:
    """
    A neighborhood node gathers filesets and generators that don't need configuring
    together.

    If it has children that are generators and need configuring then the source
    files are compiled and simulator to extract the generics/parameters for the
    configurable generator children.
    """

    def __init__(self, name, toplevel, contained_nodes, children):
        self.name = name
        self.toplevel = toplevel
        self.contained_nodes = contained_nodes
        self.needs_configuring = False
        self.children = children
        self.can_configure_parent = False
        self.work_root = self.contained_nodes[-1].work_root
        self.edalize_filename = os.path.join(self.work_root, 'edalize.yml')
        self.parameters = None
        self.generate_output = None

    def has_children_requiring_configuring(self):
        for child in self.children:
            if child.needs_configuring or child.has_children_requiring_configuring():
                return True
        return False

    def generate_before_configuring_children(self):
        return False

    def configure_parent(self, input_parameters):
        pass

    def generate(self):
        filenames = []
        for child in self.children:
            filenames += child.generate()
        filenames += [fusesoc_file_to_edalize_file(f) for f in self.get_files()]
        return filenames

    def get_files(self):
        files = []
        for node in self.contained_nodes:
            files += node.files
        return files

    def get_sim_files(self):
        files = []
        for node in self.contained_nodes:
            files += node.files
        files += self.contained_nodes[-1].sim_files
        n_vhdl_files = len([f for f in files if f.file_type=='vhdlSource'])
        n_verilog_files = len([f for f in files if f.file_type in ('verilogSource', 'systemVerilogSource')])
        if n_vhdl_files:
            assert n_verilog_files == 0
            language = 'vhdl'
        else:
            assert n_verilog_files
            language = 'verilog'
        assert not (n_vhdl_files and n_verilog_files)
        if n_verilog_files:
            language = 'verilog'
        else:
            language = 'vhdl'
        child_files = []
        for child in self.children:
            child_files += child.get_files_to_configure_from_fileset(language)
        return child_files + files

    def edalize_for_simulation(self, input_parameters):
        param_desc = {}
        for name, value in input_parameters.items():
            if isinstance(value, int):
                typ = 'int'
            else:
                raise RuntimeError('Unhandled type for parameter {}={}'.format(name, value))
            param_desc[name] = {
                'datatype': typ,
                'paramtype': 'vlogparam',
                }
        assert len(self.toplevel) == 1
        self.edalize = {
            'version': '0.2.0',
            'files': [fusesoc_file_to_edalize_file(f) for f in self.get_sim_files()],
            'hooks': {},
            'name': self.name,
            'parameters': param_desc,
            'tool_options': {},
            'toplevel': str(self.toplevel[0]),
            'vpi': [],
        }
        with open(self.edalize_filename, 'w') as f:
            f.write(yaml.dump(self.edalize))

    def configure_children(self, input_parameters):
        files_to_remove = glob.glob(os.path.join(self.work_root, 'V{}*'.format(self.name)))
        for filename in files_to_remove:
            os.remove(filename)
        self.edalize_for_simulation(input_parameters)
        tool = 'verilator'
        logger.warning('Running verilator for {} with params {}'.format(
            self.name, input_parameters))
        backend = edalize.get_edatool(tool)(
            eda_api=self.edalize, work_root=self.work_root,
        )
        args = ['--{}={}'.format(name, value) for name, value in input_parameters.items()]
        backend.configure(args)
        backend.build()
        backend.run(args)
        generator_parameters = {}
        for line in backend.get_stdout_lines():
            pieces = line.split()
            if pieces[0] == 'fusesoc-configure':
                generator = pieces[1]
                generics = json.loads(' '.join(pieces[2:]))
                if generator not in generator_parameters:
                    generator_parameters[generator] = []
                generator_parameters[generator].append(generics)
        child_output_parameters = {}
        for child in self.children:
            assert child.name not in child_output_parameters
            if child.core_name not in generator_parameters:
                logger.warning('Generator {} received no parameters from the fileset {}.  It will not be used here.'.format(
                    self.name, child.core_name))
            else:
                for params in generator_parameters[child.core_name]:
                    child_output_parameters[child.name] = child.configure(
                        params)
        return child_output_parameters

    def configure(self, input_parameters):
        if not os.path.exists(self.work_root):
            os.makedirs(self.work_root)
        if (self.needs_configuring or self.has_children_requiring_configuring() or
                self.configured_by_children):
            child_output_parameters = self.configure_children(input_parameters)
            input_parameters['child_output_parameters'] = child_output_parameters
            output_parameters = self.configure_parent(input_parameters)
            self.parameters = input_parameters
            return output_parameters
        else:
            return {}, {}


class UpdatedCore:

    def __init__(self, old_core, generators, generates, filesets):
        self.old_core = old_core
        self.generators = generators
        self.generates = generates
        self.filesets = filesets


def cores_to_nodes(cache_root, flags, cores):
    """
    Take an iterable of cores and create a node tree.
    The node tree will contain GenerateNode and FilesetNode.
    """
    all_generators = {}
    all_cores = {}
    core_top_node = {}
    new_cores = []
    for core_index, core in enumerate(cores):
        name = core.name.name
        all_cores[name] = core
        logger.debug('Processing core {}'.format(name))

        # The 'target' flag only applies to the top-level core.
        if core_index == len(cores)-1:
            target = flags['target']
        else:
            target = 'default'

        fileset_names = core.targets[target].filesets
        # sim filesets are necessary for generation because sometimes simulations
        # are run to determine the parameters to use for configurable generators.
        if 'sim' in core.targets:
            sim_fileset_names = [fs for fs in core.targets['sim'].filesets
                                 if fs not in fileset_names]
        else:
            sim_fileset_names = []
        filesets = [core.filesets[name] for name in fileset_names if core.filesets[name].files]
        sim_filesets = [core.filesets[name] for name in sim_fileset_names]

        toplevel = core.targets[target].toplevel

        generate_names = core.targets[target].generate
        generates = [core.generate[name] for name in generate_names]

        # Create generators
        generators = core.get_generators(flags)
        for generator_name, generator in generators.items():
            assert generator_name not in all_generators
            logger.debug('Creating generator {}'.format(generator_name))
            all_generators[generator_name] = make_generator(
                cache_root=cache_root,
                name=name,
                core=core,
                generator=generator,
                )

        # Create generates
        generate_nodes = []
        last_node = None
        for generate in reversed(generates):
            generator = all_generators[generate.generator]
            dependencies = [core_top_node[core_name] for core_name in generator.generator.depend]
            if last_node is not None:
                dependencies.append(last_node)
            if generator.generator.configurable_from_vhdl:
                from_vhdl_fileset = core.filesets[generator.generator.configurable_from_vhdl]
            else:
                from_vhdl_fileset = None
            if generator.generator.configurable_from_verilog:
                from_verilog_fileset = core.filesets[generator.generator.configurable_from_verilog]
            else:
                from_verilog_fileset = None
            node = GenerateNode(cache_root, core, generate, all_cores[generator.core.name.name], generator,
                                dependencies, from_vhdl_fileset, from_verilog_fileset)
            generate_nodes.append(node)
            last_node = node
            toplevel = None

        # Create filesets
        for fileset in reversed(filesets):
            dependencies = [core_top_node[core_name] for core_name in fileset.depend]
            if last_node is not None:
                dependencies.append(last_node)
            if toplevel:
                used_sim_filesets = sim_filesets
            else:
                used_sim_filesets = []
            node = FilesetNode(cache_root, core, fileset, toplevel, dependencies, used_sim_filesets)
            last_node = node
            toplevel = None

        assert name not in core_top_node
        assert node is not None
        core_top_node[name] = node

        new_cores.append(UpdatedCore(
            old_core=core,
            filesets=filesets,
            generates=generate_nodes,
            generators=generators,
            ))

    return node, new_cores


def nodes_to_neighborhoods(top_node):
    """
    Group together the FilesetNodes and generator nodes that don't need configuring into
    NeighbourhoodNodes.
    """
    children = [nodes_to_neighborhoods(child) for child in top_node.children]
    if ((not top_node.needs_configuring) and top_node.configures_children_with_fileset and
            top_node.has_children_requiring_configuring() and isinstance(top_node, GenerateNode)):
        # Node node is a configured generate, that configures it's children with
        # a fileset.
        # It makes sense just to convert it into a FilesetNode at this point.
        top_node = top_node.convert_to_fileset()
    if isinstance(top_node, GenerateNode):
        top_node.children = children
        new_node = top_node
    else:
        contained_nodes = []
        new_children = []
        for child in children:
            if isinstance(child, NeighborhoodNode):
                contained_nodes += child.contained_nodes
                new_children += child.children
            else:
                assert isinstance(child, GenerateNode)
                new_children.append(child)
        contained_nodes.append(top_node)
        # Get the correct toplevel to run a simulation during configuration.
        if top_node.toplevel:
            name = str(top_node.toplevel[0])
        else:
            name = top_node.name
        assert isinstance(name, str)
        new_node = NeighborhoodNode(name, top_node.toplevel, contained_nodes, new_children)
    return new_node


def get_new_cores(cores):
    new_cores = []
    for core_info in cores:
        old_core = core_info.old_core
        new_generates = {g.generate.name: g for g in core_info.generates}
        if not old_core.generate:
            new_cores.append(old_core)
        else:
            for generate_name, generate in old_core.generate.items():
                old_parameters = generate.parameters
                new_parameters = new_generates[generate_name].generator.parameters
                generate.parameters = {
                    'parameters': new_parameters,
                    'output_directory': new_generates[generate_name].generator.work_root,
                    }
            new_cores.append(old_core)
    return new_cores

    


