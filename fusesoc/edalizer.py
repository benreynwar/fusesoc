import logging
import os
import shutil
import yaml
import copy
import json
import glob

import edalize
from edalize import edatool

from fusesoc.vlnv import Vlnv

logger = logging.getLogger(__name__)


def fusesoc_file_to_edalize_file(fusesoc_file):
    return {
        'name': fusesoc_file.name,
        'file_type': fusesoc_file.file_type,
        'is_include_file': fusesoc_file.is_include_file,
        'logical_name': fusesoc_file.logical_name,
        }


def get_work_root(cache_root, core, fileset=None, generate=None, generator=None):
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
    working_dir = os.path.join(cache_root, 'configure', vlnv.sanitized_name)
    return working_dir


def files_from_fileset(core_root, fileset):
    files = []
    if fileset is not None:
        for f in fileset.files:
            new_f = copy.copy(f)
            if not os.path.isabs(new_f.name):
                new_f.name = os.path.join(core_root, new_f.name)
            files.append(new_f)
    return files


class Generator:

    def __init__(self, cache_root, core, generator):
        self.name = core.name.name + '_' + generator.name
        self.core_name = core.name.name
        self.core = core
        self.configured_by_children = generator.configured_by_children
        self.interpreter = generator.interpreter
        self.command = os.path.join(core.core_root, generator.command)
        self.work_root = get_work_root(
            cache_root, core, generator=generator)
        self.generator = generator
        self.parameters = []
        self.generate_output = None
        


class FilesetNode:

    def __init__(self, cache_root, core, fileset, toplevel, children, sim_filesets=None):
        self.name = core.name.name + '_' + fileset.name
        self.configured_by_parent = False
        self.configured_by_children = False
        self.children = children
        self.files = files_from_fileset(core.core_root, fileset)
        self.sim_files = []
        for sim_fileset in sim_filesets:
            self.sim_files += files_from_fileset(core.core_root, sim_fileset)
        self.toplevel = toplevel
        self.work_root = get_work_root(
            cache_root, core, fileset=fileset)


class GenerateNode:

    def __init__(self, cache_root, core, generate, generator_core, generator, children,
                 from_vhdl_fileset=None, from_verilog_fileset=None):
        self.name = core.name.name + '_' + generate.name
        self.core_name = core.name.name
        self.core = core
        self.configured_by_parent = generate.configured_by_parent
        self.configured_by_children = generator.configured_by_children
        self.interpreter = generator.interpreter
        self.command = os.path.join(generator_core.core_root, generator.command)
        self.children = children
        self.from_vhdl_fileset = from_vhdl_fileset
        self.from_verilog_fileset = from_verilog_fileset
        self.work_root = get_work_root(
            cache_root, core, generate=generate)
        self.generator = generator
        self.parameters = []
        self.generate_output = None

    def needs_to_configure_children(self):
        for child in self.children:
            if child.configured_by_parent or child.needs_to_configure_children():
                return True
        return False

    def get_gather_output_filename(self):
        filename = None
        label = 0
        while True:
            filename = os.path.join(self.work_root, 'params_{}.yml'.format(label))
            if not os.path.exists(filename):
                break
            label += 1
        return filename

    def generate_self(self):
        input_parameter_filename = os.path.join(self.work_root, 'generate_input.yaml')
        output_parameter_filename = os.path.join(self.work_root, 'generate_output.yaml')
        with open(input_parameter_filename, 'w') as handle:
            handle.write(yaml.dump(self.parameters))
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
        return output

    def generate(self):
        for child in self.children:
            child.generate()
        self.generate()

    def configure_children(self, input_parameters):
        input_parameter_filename = os.path.join(self.work_root, 'configure_input.yaml')
        output_parameter_filename = os.path.join(self.work_root, 'configure_output.yaml')
        with open(input_parameter_filename, 'w') as handle:
            handle.write(yaml.dump(input_parameters))
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
        names = [child.name for child in self.children]
        assert len(names) == len(set(names))
        child_output_parameters = {}
        generator_parameters = {}
        for child in self.children:
            child_input_parameters = output.get('child_input_parameters', {})
            for parameter_set in child_input_parameters.get(child.name, []):
                child_output_parameters[child.name], child_generator_parameters = child.configure(
                    parameter_set)
                for name, values in child_generator_parameters.items():
                    if name not in generator_parameters:
                        generator_parameters[name] = []
                    generator_parameters[name] += values
        return child_output_parameters, generator_parameters

    def configure_parent(self, input_parameters):
        input_parameter_filename = os.path.join(self.work_root, 'configure_parent_input.yaml')
        output_parameter_filename = os.path.join(self.work_root, 'configure_parent_output.yaml')
        with open(input_parameter_filename, 'w') as handle:
            dumped = yaml.dump(input_parameters)
            assert '!!' not in dumped
            handle.write(yaml.dump(input_parameters))
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
        if not os.path.exists(self.work_root):
            os.makedirs(self.work_root)
        if (self.configured_by_parent or self.needs_to_configure_children() or
                self.configured_by_children):
            logger.info('{} running configure children'.format(self.name))
            child_output_parameters, generator_parameters = self.configure_children(input_parameters)
            input_parameters['child_output_parameters'] = child_output_parameters
            if self.generator.name not in generator_parameters:
                generator_parameters[self.generator.name] = []
            generator_parameters[self.generator.name].append(input_parameters)
            self.parameters.append(input_parameters)
            logger.info('{} running configure parent'.format(self.name))
            output_parameters = self.configure_parent(input_parameters)
            logger.info('{} done with configure'.format(self.name))
        return output_parameters, generator_parameters

    def get_files_to_configure_from_fileset(self, language):
        assert language in ('vhdl', 'verilog')
        if language == 'vhdl':
            files = files_from_fileset(self.core.core_root, self.from_vhdl_fileset)
        elif language == 'verilog':
            files = files_from_fileset(self.core.core_root, self.from_verilog_fileset)
        return files


class NeighborhoodNode:

    def __init__(self, name, toplevel, contained_nodes, children):
        self.name = name
        self.toplevel = toplevel
        self.contained_nodes = contained_nodes
        self.children = children
        self.configured_by_parent = False
        self.configured_by_children = False
        self.work_root = self.contained_nodes[-1].work_root
        self.edalize_filename = os.path.join(self.work_root, 'edalize.yml')
        self.parameters = None
        self.generate_output = None

    def needs_to_configure_children(self):
        for child in self.children:
            if child.configured_by_parent or child.needs_to_configure_children():
                return True
        return False

    def configure_parent(self, input_parameters):
        pass

    def generate(self):
        for child in self.children:
            child.generate()

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
            'version'      : '0.2.0',
            'files'        : [fusesoc_file_to_edalize_file(f)
                              for f in self.get_sim_files()],
            'hooks'        : {},
            'name'         : self.name,
            'parameters'   : param_desc,
            'tool_options' : {},
            'toplevel'     : str(self.toplevel[0]),
            'vpi'          : [],
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
        output_generator_parameters = {}
        for child in self.children:
            if child.core_name not in generator_parameters:
                raise RuntimeError('The generator {} expected to receive generic parameters from fileset {} but none were recieved.'.format(self.name, child.core_name))
            assert child.name not in child_output_parameters
            for params in generator_parameters[child.core_name]:
                child_output_parameters[child.name], child_generator_parameters = child.configure(
                    params)
                for name, values in child_generator_parameters.items():
                    if name not in output_generator_parameters:
                        output_generator_parameters[name] = []
                    output_generator_parameters[name] += values
        return child_output_parameters, output_generator_parameters

    def configure(self, input_parameters):
        if not os.path.exists(self.work_root):
            os.makedirs(self.work_root)
        if (self.configured_by_parent or self.needs_to_configure_children() or
                self.configured_by_children):
            child_output_parameters, generator_parameters = self.configure_children(input_parameters)
            input_parameters['child_output_parameters'] = child_output_parameters
            output_parameters = self.configure_parent(input_parameters)
            self.parameters = input_parameters
            return output_parameters, generator_parameters
        else:
            return {}, {}


def cores_to_nodes(cache_root, flags, cores):
    all_generators = {}
    all_cores = {}
    core_top_node = {}
    for core_index, core in enumerate(cores):
        name = core.name.name
        print(core_index, name)
        if core_index == len(cores)-1:
            target = flags['target']
        else:
            target = 'default'
        fileset_names = core.targets[target].filesets
        if 'sim' in core.targets:
            sim_fileset_names = [fs for fs in core.targets['sim'].filesets if fs not in fileset_names]
        else:
            sim_fileset_names = []
        generate_names = core.targets[target].generate
        toplevel = core.targets[target].toplevel
        filesets = [core.filesets[name] for name in fileset_names if core.filesets[name].files]
        sim_filesets = [core.filesets[name] for name in sim_fileset_names]
        generates = [core.generate[name] for name in generate_names]
        generator_names = [g.generator for g in generates]
        generators = core.get_generators(flags)
        for generator_name, generator in generators.items():
            assert generator_name not in all_generators
            print('saving generator {}'.format(generator_name))
            all_generators[generator_name] = (name, generator)
        all_cores[name] = core
        last_node = None
        for generate in reversed(generates):
            generator_core, generator = all_generators[generate.generator]
            dependencies = [core_top_node[core_name] for core_name in generator.depend]
            if last_node is not None:
                dependencies.append(last_node)
            if generator.configurable_from_vhdl:
                from_vhdl_fileset = core.filesets[generator.configurable_from_vhdl]
            else:
                from_vhdl_fileset = None
            if generator.configurable_from_verilog:
                from_verilog_fileset = core.filesets[generator.configurable_from_verilog]
            else:
                from_verilog_fileset = None
            node = GenerateNode(cache_root, core, generate, all_cores[generator_core], generator, dependencies,
                                from_vhdl_fileset, from_verilog_fileset)
            last_node = node
            toplevel = None
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
    return node


def nodes_to_neighborhoods(top_node):
    children = [nodes_to_neighborhoods(child) for child in top_node.children]
    if top_node.configured_by_parent:
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
                assert child.configured_by_parent
                new_children.append(child)
        contained_nodes.append(top_node)
        if top_node.toplevel:
            name = str(top_node.toplevel[0])
        else:
            name = top_node.name
        assert isinstance(name, str)
        new_node = NeighborhoodNode(name, top_node.toplevel, contained_nodes, new_children)
    return new_node


class Edalizer(object):

    def __init__(self, vlnv, flags, cores, cache_root, work_root, export_root=None):
        if os.path.exists(work_root):
            for f in os.listdir(work_root):
                if os.path.isdir(os.path.join(work_root, f)):
                    shutil.rmtree(os.path.join(work_root, f))
                else:
                    os.remove(os.path.join(work_root, f))
        else:
            os.makedirs(work_root)

        logger.debug("Building EDA API")
        def merge_dict(d1, d2):
            for key, value in d2.items():
                if isinstance(value, dict):
                    d1[key] = merge_dict(d1.get(key, {}), value)
                elif isinstance(value, list):
                    d1[key] = d1.get(key, []) + value
                else:
                    d1[key] = value
            return d1

        generators   = {}

        first_snippets = []
        snippets       = []
        last_snippets  = []
        _flags = flags.copy()
        top_node = cores_to_nodes(cache_root, _flags, cores)
        top_node = nodes_to_neighborhoods(top_node)
        if not os.path.exists(top_node.work_root):
            os.makedirs(top_node.work_root)
        top_parameters = {'width': 32, 'tap0': 15, 'tap1': 37}
        response_parameters, generator_parameters = top_node.configure(top_parameters)
        import pdb
        pdb.set_trace()
        core_queue = cores[:]
        core_queue.reverse()
        while core_queue:
            snippet = {}
            core = core_queue.pop()
            logger.info("Preparing " + str(core.name))
            core.setup()

            logger.debug("Collecting EDA API parameters from {}".format(str(core.name)))
            _flags['is_toplevel'] = (core.name == vlnv)

            #Extract files
            if export_root:
                files_root = os.path.join(export_root, core.sanitized_name)
                core.export(files_root, _flags)
            else:
                files_root = core.files_root

            rel_root = os.path.relpath(files_root, work_root)

            #Extract parameters
            snippet['parameters'] = core.get_parameters(_flags)

            #Extract tool options
            snippet['tool_options'] = {flags['tool'] : core.get_tool_options(_flags)}

            #Extract scripts
            snippet['scripts'] = core.get_scripts(rel_root, _flags)

            _files = []
            for file in core.get_files(_flags):
                if file.copyto:
                    _name = file.copyto
                    dst = os.path.join(work_root, _name)
                    _dstdir = os.path.dirname(dst)
                    if not os.path.exists(_dstdir):
                        os.makedirs(_dstdir)
                    shutil.copy2(os.path.join(files_root, file.name),
                                 dst)
                else:
                    _name = os.path.join(rel_root, file.name)
                _files.append({
                    'name'            : _name,
                    'file_type'       : file.file_type,
                    'is_include_file' : file.is_include_file,
                    'logical_name'    : file.logical_name})

            snippet['files'] = _files

            #Extract VPI modules
            snippet['vpi'] = []
            for _vpi in core.get_vpi(_flags):
                snippet['vpi'].append({'name'         : _vpi['name'],
                                       'src_files'    : [os.path.join(rel_root, f) for f in _vpi['src_files']],
                                       'include_dirs' : [os.path.join(rel_root, i) for i in _vpi['include_dirs']],
                                       'libs'         : _vpi['libs']})

            #Extract generators if defined in CAPI
            if hasattr(core, 'get_generators'):
                generators.update(core.get_generators(_flags))

            #Run generators
            if hasattr(core, 'get_ttptttg'):
                for ttptttg_data in core.get_ttptttg(_flags):
                    _ttptttg = Ttptttg(ttptttg_data, core, generators)
                    for gen_core in _ttptttg.generate(cache_root):
                        gen_core.pos = _ttptttg.pos
                        core_queue.append(gen_core)

            if hasattr(core, 'pos'):
                if core.pos == 'first':
                    first_snippets.append(snippet)
                elif core.pos == 'last':
                    last_snippets.append(snippet)
                else:
                    snippets.append(snippet)
            else:
                snippets.append(snippet)

        top_core = cores[-1]
        self.edalize = {
            'version'      : '0.2.0',
            'files'        : [],
            'hooks'        : {},
            'name'         : top_core.sanitized_name,
            'parameters'   : {},
            'tool_options' : {},
            'toplevel'     : top_core.get_toplevel(flags),
            'vpi'          : [],
        }

        for snippet in first_snippets + snippets + last_snippets:
            merge_dict(self.edalize, snippet)

    def to_yaml(self, edalize_file):
        with open(edalize_file,'w') as f:
            f.write(yaml.dump(self.edalize))

from fusesoc.core import Core
from fusesoc.utils import Launcher

class Ttptttg(object):

    def __init__(self, ttptttg, core, generators):
        generator_name = ttptttg['generator']
        if not generator_name in generators:
            raise RuntimeError("Could not find generator '{}' requested by {}".format(generator_name, core.name))
        self.generator = generators[generator_name]
        self.name = ttptttg['name']
        self.pos = ttptttg['pos']
        parameters = ttptttg['config']

        vlnv_str = ':'.join([core.name.vendor,
                             core.name.library,
                             core.name.name+'-'+self.name,
                             core.name.version])
        self.vlnv = Vlnv(vlnv_str)


        self.generator_input = {
            'files_root' : os.path.abspath(core.files_root),
            'gapi'       : '1.0',
            'parameters' : parameters,
            'vlnv'       : vlnv_str,
        }

    def generate(self, cache_root):
        """Run a parametrized generator

        Args:
            cache_root (str): The directory where to store the generated cores

        Returns:
            list: Cores created by the generator
        """
        generator_cwd = os.path.join(cache_root, 'generated', self.vlnv.sanitized_name)
        generator_input_file  = os.path.join(generator_cwd, self.name+'_input.yml')

        logger.info('Generating ' + str(self.vlnv))
        if not os.path.exists(generator_cwd):
            os.makedirs(generator_cwd)
        with open(generator_input_file, 'w') as f:
            f.write(yaml.dump(self.generator_input))

        args = [os.path.join(os.path.abspath(self.generator.root), self.generator.command),
                generator_input_file]

        if self.generator.interpreter:
            args[0:0] = [self.generator.interpreter]

        Launcher(args[0], args[1:],
                 cwd=generator_cwd).run()

        cores = []
        logger.debug("Looking for generated cores in " + generator_cwd)
        for root, dirs, files in os.walk(generator_cwd):
            for f in files:
                if f.endswith('.core'):
                    try:
                        cores.append(Core(os.path.join(root, f)))
                    except SyntaxError as e:
                        w = "Failed to parse generated core file " + f + ": " + e.msg
                        raise RuntimeError(w)
        logger.debug("Found " + ', '.join(str(c.name) for c in cores))
        return cores
