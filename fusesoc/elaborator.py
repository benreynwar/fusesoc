import os
import logging
from configparser import ConfigParser

from fusesoc.coremanager import CoreManager
from fusesoc.config import Config
from fusesoc.vlnv import Vlnv
try:
    from io import StringIO
except ImportError:
    from StringIO import StringIO

from fusesoc.edatool import EdaTool

logger = logging.getLogger(__name__)


def get_cores(core_name):
    '''
    Returns a list of cores required for a given core name.
    The top level core is the last in the list.
    '''
    core = CoreManager().get_core(Vlnv(core_name))
    cores = CoreManager().get_depends(core.name)
    return cores


def setup_cores(cores):
    '''
    Runs all the providers for the cores.
    This retrieves remote files and does any generation that
    does not depend on parameters
    '''
    for core in cores:
        core.setup()


def generate_packages(cores, params, working_dir):
    '''
    Generates files for packages that depend on top-level parameters
    only.
    '''
    for core in cores:
        if core.package_generator:
            core.package_generator.generate(params, working_dir)


def get_files(cores, working_dir):
    incdirs = []
    src_files = []
    usage = 'synth'
    for core in cores:
        files_root = core.files_root
        basepath = os.path.relpath(files_root, working_dir)
        for fs in core.file_sets:
            # FIXME: We ignore private filesets for know.
            if (set(fs.usage) & set(usage)) and (not fs.private):
                for file in fs.file:
                    if file.is_include_file:
                        incdir = os.path.join(basepath, os.path.dirname(file.name))
                        if incdir not in incdirs:
                            incdirs.append(incdir)
                    else:
                        new_file = file.copy()
                        new_file.name = os.path.join(basepath, file.name)
                        src_files.append(new_file)
    return (src_files, incdirs)


class Elaborator(EdaTool):
    '''
    Elaborator is used to resolve dependencies and generate a core file that
    lists all files explicitly.
    This is useful when using fusesoc as a build system since the generated
    core file can be used by other tools to determine the required files.
    '''

    TOOL_TYPE = 'elab'

    def __init__(self, system, export):
        super(Elaborator, self).__init__(system, export)
        logger.debug("depend -->  " + str(self.cores))
        self.filesets = {
            'sim': self._get_fileset_files(['sim'])[0],
            'synth': self._get_fileset_files(['synth'])[0],
            }

    def labels_to_file_list(self, labels, exclude=[]):
        if exclude:
            exclude_fs = self.labels_to_file_list(exclude)
        else:
            exclude_fs = []
        filesets = [self.filesets[label] for label in labels]
        fs = []
        for fileset in filesets:
            fnames = [os.path.abspath(os.path.join(self.work_root, f.name))
                      for f in fileset]
            fs += [fname for fname in fnames if fname not in exclude_fs]
        return fs

    def get_missing_instances(self):
        # Run ghdl are get the GenericsLog messages.
        # Rerun the approripate providers with updated params.
        # Run ghdl to see if anymore messages.
        # Iterate until no more messages.
        pass

    def make_core_file(self):
        self.configure({})
        p = ConfigParser()
        # Main info
        p.add_section('main')
        p.set('main', 'name', self.system.sanitized_name)
        # Synthesisable files
        p.add_section('fileset rtl')
        synth_files = self.labels_to_file_list(['synth'])
        p.set('fileset rtl', 'files', '\n'.join(synth_files))
        # Testbench files
        p.add_section('fileset tb')
        tb_files = self.labels_to_file_list(['sim'], exclude=['synth'])
        p.set('fileset tb', 'files', '\n'.join(tb_files))
        output = StringIO()
        p.write(output)
        txt = 'CAPI=1\n'
        txt += output.getvalue()
        return txt

    def write_core_file(self, fn):
        txt = self.make_core_file()
        with open(fn, 'w') as f:
            f.write(txt)
