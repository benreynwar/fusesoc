#FIXME: IP-XACT support
#Default simulator
#Fix backends to not assume all tool_options exist
import importlib
import logging
import os
from pyparsing import Forward, OneOrMore, Optional, Suppress, Word, alphanums
import shutil
import yaml

from ipyxact.ipyxact import Component
from fusesoc import utils
from fusesoc.config import Config
from fusesoc.vlnv import Vlnv

logger = logging.getLogger(__name__)

class File(object):
    def __init__(self, tree):
        self.file_type = ''
        self.is_include_file = False
        if type(tree) is dict:
            for k, v in tree.items():
                self.name = k
                if 'file_type' in v:
                    self.file_type = v['file_type']
                if 'is_include_file' in v:
                    self.is_include_file = v['is_include_file']
        else:
            self.name = tree
            self.is_include_file = False #"FIXME"

class String(str):
    def parse(self, flags):
        _flags = []
        for k,v in flags.items():
            if v == True:
                _flags.append(k)
            elif v in [False, None]:
                pass
            else:
                _flags.append(k+'_'+v)
        logger.debug("Parsing '{}' with flags {}".format(self.__str__(),
                                                  str(_flags)))

        def cb_conditional(s,l,t):
            if (t.cond in _flags) != (t.negate == '!'):
                return t.expr
            else:
                return []
        word = Word(alphanums+':>.[]_-,=~/')
        conditional = Forward()
        conditional << (Optional("!")("negate") + word("cond") + Suppress('?') + Suppress('(') + OneOrMore(conditional ^ word)("expr") + Suppress(')')).setParseAction(cb_conditional)
        #string = (function ^ word)
        string = word
        string_list = OneOrMore(conditional ^ string)
        return ' '.join(string_list.parseString(self.__str__()))

class Section(object):
    members = {}
    lists   = {}
    dicts   = {}
    def __init__(self, tree):
        for k, v in tree.items():
            if k in self.members:
                setattr(self, k, globals()[self.members[k]](v))
            elif k in self.lists:
                _l = []
                for _item in v:
                    try:
                        _l.append(globals()[self.lists[k]](_item))
                    except TypeError as e:
                        raise SyntaxError("Bad option '{}' in section '{}'".format(_item, k))
                setattr(self, k, _l)
            elif k in self.dicts:
                _d = {}
                for _name, _items in v.items():
                    try:
                        _d[_name] = globals()[self.dicts[k]](_items)
                    except AttributeError as e:
                        raise SyntaxError("Bad option '{}' in section '{}'".format(_name, k))
                setattr(self, k, _d)
            else:
                raise KeyError(k + " in section " + self.__class__.__name__)
    
class Provider(object):
    def __new__(cls, *args, **kwargs):
        provider_name = args[0]['name']
        if provider_name is None:
            raise RuntimeError('Missing "name" in section [provider]')
        provider_module = importlib.import_module(
            'fusesoc.provider.%s' % provider_name)
        return provider_module.PROVIDER_CLASS(args[0],
                                              "FIXME: core_root is used by local providers",
                                             "FIXME: cache_root can be set in fetch call")

class Core:
    def __init__(self, core_file):
        basename = os.path.basename(core_file)

        self.core_root = os.path.dirname(core_file)

        try:
            _root = Root(yaml.load(open(core_file)))
        except KeyError as e:
            raise RuntimeError("Error parsing '{}'. Unknown item {}".format(core_file, e))

        for i in _root.members:
            setattr(self, i, getattr(_root, i))
        for i in _root.lists:
            setattr(self, i, getattr(_root, i))
        for i in _root.dicts:
            setattr(self, i, getattr(_root, i))

        self.export_files = []
        if not self.name:
            raise SyntaxError("Missing 'name' parameter")
        self.sanitized_name = self.name.sanitized_name

        #self.backend = getattr(self, self.main.backend)

        for fs in self.filesets.values():
            if fs.file_type:
                for f in fs.files:
                    if not f.file_type:
                        f.file_type = fs.file_type

        for fs in self.filesets.values():
            for f in fs.files:
                f.logical_name = fs.logical_name
        for k, v in self.targets.items():
            setattr(v, 'name', k)

                
        if self.provider:
            self.files_root = os.path.join(Config().cache_root,
                                           self.sanitized_name)
            #Ugly hack. Don't like injecting vars
            #How about a setup function or setters?
            self.provider.core_root  = self.core_root
            self.provider.files_root = self.files_root
        else:
            self.files_root = self.core_root

        self.scripts = [] #FIXME

    def cache_status(self):
        if self.provider:
            return self.provider.status()
        else:
            return 'local'

    def export(self, dst_dir, flags={}):
        if os.path.exists(dst_dir):
            shutil.rmtree(dst_dir)

        src_files = [f.name for f in self.get_files(flags)]

        
        for k, v in self._get_vpi(flags).items():
            src_files += [f.name for f in v['src_files'] + v['inc_files']] #FIXME include files
        self._debug("Exporting {}".format(str(src_files)))

        #for fs in self._get_filesets(flags):
        #    src_files += [f.name for f in fs.files]
        dirs = list(set(map(os.path.dirname,src_files)))
        for d in dirs:
            if not os.path.exists(os.path.join(dst_dir, d)):
                os.makedirs(os.path.join(dst_dir, d))

        for f in src_files:
            if not os.path.isabs(f):
                if(os.path.exists(os.path.join(self.core_root, f))):
                    shutil.copyfile(os.path.join(self.core_root, f),
                                    os.path.join(dst_dir, f))
                elif (os.path.exists(os.path.join(self.files_root, f))):
                    shutil.copyfile(os.path.join(self.files_root, f),
                                    os.path.join(dst_dir, f))
                else:
                    raise RuntimeError('Cannot find %s in :\n\t%s\n\t%s'
                                  % (f, self.files_root, self.core_root))

    def get_scripts(self, flags):
        return {} #FIXME

    def get_tool(self, flags):
        tool = None
        if flags['tool']:
            return flags['tool']
        elif 'target' in flags:
            target = self._get_target(flags)
            if flags['flow'] == 'sim':
                return target.default_sim
        elif flags['flow'] == 'synth':
            return 'quartus' #FIXME Need to get default tool from .core file

    def get_tool_options(self, flags):
        _flags = flags.copy()
        #_flags['is_toplevel'] = True #FIXME: Is this correct? No! This gets the wrong target for non-toplevel cores. What was the idea behind this?? Can't remember
        self._debug("Getting tool options for flags {}".format(str(_flags)))
        target = self._get_target(_flags)
        if target:
            section = getattr(target, flags['tool'])
        else:
            section = None

        options = {}
        if section:
            for member in section.members:
                if hasattr(section, member):
                    options[member] = getattr(section, member).split() #FIXME: Should this always be a list?
        self._debug("Found tool options {}".format(str(options)))
        return options

    def get_depends(self, flags): #Add use flags?
        depends = []
        self._debug("Getting dependencies for flags {}".format(str(flags)))
        for fs in self._get_filesets(flags):
            depends += [Vlnv(d) for d in self._parse_list(flags, fs.depend)]
        return depends

    def get_files(self, flags):
        src_files = []
        for fs in self._get_filesets(flags):
            src_files += fs.files
        return src_files

    def get_parameters(self, flags={}):
        self._debug("Getting parameters for flags '{}'".format(str(flags)))
        target = self._get_target(flags)
        parameters = []

        if target:
            for p in self._parse_list(flags, target.parameters):
                _p = self.parameters[p]
                _p.name = p
                parameters.append(_p)
        self._debug("Found parameters {}".format(parameters))
        return parameters

    def get_toplevel(self, flags):
        _flags = flags.copy()
        _flags['is_toplevel'] = True #FIXME: Is this correct?
        self._debug("Getting toplevel for flags {}".format(str(_flags)))
        target = self._get_target(_flags)
        toplevel = target.toplevel
        if not toplevel:
            raise SyntaxError("Target '{}' has no toplevel".format(target.name))
        return toplevel

    def _get_vpi(self, flags):
        vpi = {}
        target = self._get_target(flags)
        if not target:
            return vpi
        for vpi_name in self._parse_list(flags, target.vpi):
            vpi_lib = self.vpi[vpi_name]
            files = []
            incfiles = [] #Really do this automatically?
            for fs in vpi_lib.filesets:
                for f in self.filesets[fs].files:
                    if f.is_include_file:
                        incfiles.append(f)
                    else:
                        files.append(f)
            vpi[vpi_name] = {'src_files' : files,
                             'inc_files' : incfiles,
                             'libs'      : vpi_lib.libs}
        return vpi

    def get_vpi(self, flags):
        self._debug("Getting VPI libraries for flags {}".format(flags))
        target = self._get_target(flags)
        vpi = []
        _vpi = self._get_vpi(flags)
        self._debug(" Matched VPI libraries {}".format([v for v in _vpi]))
        for k, v in _vpi.items():
            vpi.append({'name'         : k,
                        'src_files'    : v['src_files'],
                        'include_dirs' : utils.unique_dirs(v['inc_files']),
                        'libs'         : v['libs'],
            })
        return vpi

    def info(self):
        s = """CORE INFO
Name:                   {}
Core root:              {}

File sets:
{}
"""
        return s.format(str(self.name),
                        str(self.core_root),
                        "FIXME")
        #FIXME: Start from root and recursively go down the tree
        filesets = ""
        for k,v in self.filesets.items():
            print("""
 Name  : {}
 Files :""".format(k))
            if not v.files:
                print(" <No files>")
            else:
                _longest_name = max([len(x.name) for x in v.files])
                _longest_type = max([len(x.file_type) for x in v.files])
                for f in v.files:
                    print("  {} {} {}".format(f.name.ljust(_longest_name),
                                              f.file_type.ljust(_longest_type),
                                              "(include file)" if f.is_include_file else ""))
        print("Targets")
        print("=======")
        for target in self.targets:
            print(target)
        print("=======")

    def patch(self, dst_dir):
        #FIXME: Use native python patch instead
        patches = self.provider.patches
        for f in patches:
            patch_file = os.path.abspath(os.path.join(self.core_root, f))
            if os.path.isfile(patch_file):
                self._debug("  applying patch file: " + patch_file + "\n" +
                             "                   to: " + os.path.join(dst_dir))
                try:
                    utils.Launcher('git', ['apply', '--unsafe-paths',
                                     '--directory', os.path.join(dst_dir),
                                     patch_file]).run()
                except OSError:
                    print("Error: Failed to call external command 'patch'")
                    return False
        return True

    def setup(self):
        if self.provider:
            if self.provider.fetch():
                self.patch(self.files_root)

    def _debug(self, msg):
        logger.debug("{} : {}".format(str(self.name), msg))

    def _get_target(self, flags):
        self._debug(" Resolving target for flags '{}'".format(str(flags)))

        target_name = None
        if flags['flow'] in self.targets:
            target_name = flags['flow']
        if 'is_toplevel' in flags and flags['is_toplevel']:
            if 'target' in flags and flags['target']:
                target_name = flags['target']
            else:
                _target_name = getattr(self, 'default_'+flags['flow']+'_target')
                if _target_name:
                    target_name = _target_name

        if target_name:
            self._debug(" Matched target {}".format(target_name))
            try:
                return self.targets[target_name]
            except KeyError:
                msg = "Target '{}' does not exist in '{}'"
                raise SyntaxError(msg.format(target_name, str(self.name)))
        else:
            logger.debug(" Matched no target")
            return None

    def _get_filesets(self, flags):
        self._debug("Getting filesets for flags '{}'".format(str(flags)))
        target = self._get_target(flags)
        if not target:
            return []
        filesets = []

        for fs in target.filesets:
            _fs = fs.parse(flags)
            if not _fs in self.filesets:
                raise SyntaxError("Fileset '{}', requested by fileset '{}', was not found".format(_fs, target.name))
            filesets.append(self.filesets[_fs])

        self._debug(" Matched filesets {}".format(target.filesets))
        return filesets

    def _parse_component(self, component_file):
        component = Component()
        component.load(component_file)

        if not self.main.description:
            self.main.description = component.description

        _file_sets = []
        for file_set in component.fileSets.fileSet:
            _name = file_set.name
            for f in file_set.file:
                self.export_files.append(f.name)
                #FIXME: Harmonize underscore vs camelcase
                f.file_type = f.fileType
                if f.isIncludeFile == 'true':
                    f.is_include_file = True
                else:
                    f.is_include_file = False
                f.logical_name = f.logicalName
            #FIXME: Handle duplicates. Resolution function? (merge/replace, prio ipxact/core)
            _taken = False
            for fs in self.file_sets:
                if fs.name == file_set.name:
                    _taken = True
            if not _taken:
                _file_sets.append(FileSet(name = file_set.name,
                                          file = file_set.file[:],
                                          usage = ['sim', 'synth']))
        self.file_sets += _file_sets

    def _parse_list(self, flags, l):
        return [x.parse(flags) for x in l if x.parse(flags)]
description = """
---
Root:
  members:
    name        : Vlnv
    description : String
    provider    : Provider
    CAPI=2      : String
    scripts     : Scripts
    default_sim_target : String
  dicts:
    filesets   : Fileset
    targets    : Target
    parameters : Parameter
    vpi        : Vpi

Fileset:
  members:
    file_type    : String
    logical_name : String
  lists:
    files      : File
    depend     : String

Target:
  members:
    default_sim : String
    toplevel : String
    icarus   : Icarus
    modelsim : Modelsim
    quartus  : Quartus
  lists:
    filesets   : String
    parameters : String
    vpi        : String

Parameter:
  members:
    datatype : String
    default  : String
    description : String
    paramtype   : String
    scope       : String

Icarus:
  members:
    iverilog_options : String

Quartus:
  members:
    quartus_options : String
    family          : String
    device          : String

Modelsim:
  members:
    vlog_options    : String
    vsim_options    : String

Scripts:
  lists:
    pre_build  : String
    post_build : String
    pre_run    : String
    post_run   : String
Vpi:
  lists:
    libs         : String
    filesets : String
  
"""

def _generate_classes(j, base_class):
    for cls, _items in j.items():
        class_members = {}
        if 'members' in _items:
            for key in _items['members']:
                class_members[key] = None
            class_members['members'] = _items['members']
        if 'lists' in _items:
            for key in _items['lists']:
                class_members[key] = []
            class_members['lists'] = _items['lists']
        if 'dicts' in _items:
            for key in _items['dicts']:
                class_members[key] = {}
            class_members['dicts'] = _items['dicts']

        generatedClass = type(cls, (base_class,), class_members)
        globals()[generatedClass.__name__] = generatedClass

_generate_classes(yaml.load(description), Section)
