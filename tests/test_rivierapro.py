import os
import shutil
import pytest

from test_common import compare_file, get_core, get_sim, sim_params

tests_dir = os.path.dirname(__file__)
core      = get_core("mor1kx-generic")
backend   = get_sim('rivierapro', core)
#backend.toplevel = backend.system.simulator['toplevel']
ref_dir   = os.path.join(tests_dir, __name__)
work_root = backend.work_root

def test_rivierapro_configure():

    backend.configure(sim_params)

    assert '' == compare_file(ref_dir, work_root, 'fusesoc_build_rtl.tcl')
    assert '' == compare_file(ref_dir, work_root, 'fusesoc_build_vpi.tcl')
    assert '' == compare_file(ref_dir, work_root, 'fusesoc_launch.tcl')
    assert '' == compare_file(ref_dir, work_root, 'fusesoc_main.tcl')
    assert '' == compare_file(ref_dir, work_root, 'fusesoc_run.tcl')
