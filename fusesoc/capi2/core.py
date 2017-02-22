#FIXME: IP-XACT support
#Default simulator
#Fix backends to not assume all tool_options exist
import importlib
import logging
import os
from pyparsing import OneOrMore, Optional, Suppress, Word, alphas
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
        def cb_conditional(s,l,t):
            if (t.cond in flags) != (t.negate == '!'):
                return t.expr
            else:
                return []
        word = Word(alphas+'.[]_,=~/')
        conditional = (Optional("!")("negate") + word("cond") + Suppress('?') + Suppress('(') + OneOrMore(word)("expr") + Suppress(')')).setParseAction(cb_conditional)
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
                    _l.append(globals()[self.lists[k]](_item))
                setattr(self, k, _l)
            elif k in self.dicts:
                _d = {}
                for _name, _items in v.items():
                    _d[_name] = globals()[self.dicts[k]](_items)
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

        self.sanitized_name = self.name.sanitized_name
        self.vpi = {} #FIXME

        #self.backend = getattr(self, self.main.backend)

        for fs in self.filesets.values():
            if fs.file_type:
                for f in fs.files:
                    if not f.file_type:
                        f.file_type = fs.file_type
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

        target = self._get_target(flags)
        src_files = [f.name for f in self.get_files(flags)]
        logger.debug("Exporting {}".format(str(src_files)))

        for fs in self._get_filesets(flags):
            src_files += [f.name for f in fs.files]

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

    def get_tool(self, flags):
        if flags['tool']:
            return flags['tool']
        elif flags['flow'] == 'synth':
            return 'quartus' #FIXME Need to get default tool from .core file
        else:
            return None #FIXME Need to get default tool from .core file

    def get_tool_options(self, flags):
        _flags = flags.copy()
        _flags['is_toplevel'] = True #FIXME: Is this correct?
        logger.debug("Getting tool options for flags {}".format(str(_flags)))
        target = self._get_target(_flags)
        section = getattr(target, flags['tool'])

        if not section:
            return {}
        options = {}
        for member in section.members:
            if hasattr(section, member):
                options[member] = getattr(section, member)
        return options

    def get_depends(self, flags): #Add use flags?
        depends = []
        logger.debug("Getting dependencies for flags {}".format(str(flags)))
        for fs in self._get_filesets(flags):
            depends += fs.depend
        return depends

    def get_files(self, flags):
        src_files = []
        for fs in self._get_filesets(flags):
            src_files += fs.files
        return src_files

    def get_parameters(self, flags={}):
        target = self._get_target(flags)
        logger.debug("Getting parameters for target '{}'".format(target))
        parameters = []

        for p in target.use_parameters:
            _p = self.parameters[p.parse(flags)]
            _p.name = p.parse(flags)
            parameters.append(_p)
        return parameters

    def get_toplevel(self, flags={}):
        _flags = flags.copy()
        _flags['is_toplevel'] = True #FIXME: Is this correct?
        logger.debug("Getting toplevel for flags {}".format(str(_flags)))
        return self._get_target(_flags).toplevel

    def info(self):
        show_list = lambda l: "\n                        ".join([str(x) for x in l])
        show_dict = lambda d: show_list(["%s: %s" % (k, d[k]) for k in d.keys()])

        print("CORE INFO")
        print("Name:                   " + str(self.name))
        print("Core root:              " + self.core_root)

        #FIXME: Start from root and recursively go down the tree
        print("File sets:")
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
    def patch(self, dst_dir):
        #FIXME: Use native python patch instead
        patch_root = os.path.join(self.core_root, 'patches')
        patches = self.main.patches
        if os.path.exists(patch_root):
            for p in sorted(os.listdir(patch_root)):
                patches.append(os.path.join('patches', p))

        for f in patches:
            patch_file = os.path.abspath(os.path.join(self.core_root, f))
            if os.path.isfile(patch_file):
                logger.debug("  applying patch file: " + patch_file + "\n" +
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

    def _get_target(self, flags):
        logger.debug("Getting target for flags '{}'".format(str(flags)))
        if 'is_toplevel' in flags and flags['is_toplevel'] and 'target' in flags and flags['target']:
            target_name = flags['target']
        else:
            target_name = flags['flow']
        logger.debug("Matched target {}".format(target_name))

        return self.targets[target_name]

    def _get_filesets(self, flags):
        logger.debug("Getting filesets for flags '{}'".format(str(flags)))
        target = self._get_target(flags)
        filesets = []

        for fs in target.use_filesets:
            filesets.append(self.filesets[fs.parse(flags)])
        logger.debug("Matched filesets {}".format(target.use_filesets))
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


description = """
---
Root:
  members:
    name        : Vlnv
    description : String
    provider    : Provider
    CAPI=2      : String
  dicts:
    filesets   : Fileset
    targets    : Target
    parameters : Parameter

Fileset:
  members:
    file_type   : String
  lists:
    files      : File
    depend     : Vlnv

Target:
  members:
    toplevel : String
    icarus   : Icarus
    modelsim : Modelsim
    quartus  : Quartus
  lists:
    use_filesets   : String
    use_parameters : String
    use_vpi        : String

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

Vpi:
  members:
    filesets : String
    libs     : String
  
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
