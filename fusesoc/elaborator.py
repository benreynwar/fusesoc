import os
import logging
from configparser import ConfigParser
try:
    from io import StringIO
except ImportError:
    from StringIO import StringIO

from fusesoc.edatool import EdaTool

logger = logging.getLogger(__name__)


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

    def make_core_file(self):
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
