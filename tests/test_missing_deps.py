import os

from fusesoc.vlnv import Vlnv
from fusesoc.coremanager import CoreManager

cm = CoreManager()
tests_dir = os.path.dirname(__file__)
cores_root = os.path.join(tests_dir, 'cores')
cm.add_cores_root(cores_root)

def test_missing_deps():
    flags = {
        'flow': 'sim',
        'tool': 'ghdl',
        }
    cores = cm.get_depends(Vlnv('missing_deps'), flags=flags)
