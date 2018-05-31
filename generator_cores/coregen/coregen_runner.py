#!/usr/bin/env python
import os
import shutil
import subprocess
import sys
import yaml

import xml.etree.ElementTree as ET

def parse_cgc(f):
    nsmap = {'spirit' : "http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009",
             'xilinx' : "http://www.xilinx.com"}
    tree = ET.parse(f)
    root = tree.getroot()
    file_type_map = {
        'ucf' : 'UCF',
        'verilog' : 'verilogSource'
    }
    files = []
    for fileset in root.findall('./spirit:componentInstances/spirit:componentInstance/spirit:vendorExtensions/xilinx:generationHistory/*', nsmap):
        fsname = fileset.find('./xilinx:name', nsmap).text
        if fsname == 'implementation_source_generator':
            for ff in fileset.findall('./xilinx:file', nsmap):
                fname = ff.find('./xilinx:name', nsmap).text
                ftypes = [ftype.text for ftype in ff.findall('./xilinx:userFileType', nsmap)]
                if not 'ignore' in ftypes:
                    files.append({fname : {
                        'file_type' : file_type_map.get(ftypes[0], 'user')
                    }})
    return files

with open(sys.argv[1]) as f:
    data = yaml.load(f)

    config     = data['parameters']
    files_root = data['files_root']

    subdir = config.get('chroot', '')
    script_file  = os.path.relpath(config.get('script_file'), subdir)
    project_file = os.path.relpath(config.get('project_file'), subdir)
    src_files = [script_file, project_file]
    for f in config.get('extra_files', []):
        src_files.append(os.path.relpath(f, subdir))
    core_name = os.path.splitext(os.path.basename(script_file))[0]
    core_file = config.get('core_file', core_name+'.core')
    vlnv      = '::'+core_name+':0'

    for f in src_files:
        f_src = os.path.join(files_root, subdir, f)
        if os.path.exists(f_src):
            d_dst = os.path.dirname(f)
            if d_dst and not os.path.exists(d_dst):
                os.makedirs(d_dst)
            shutil.copyfile(f_src, f)

    args = ['-r',
            '-b', script_file,
            '-p', project_file]
    rc = subprocess.call(['coregen'] + args)

    with open(core_file, 'w') as f:
        files = parse_cgc(project_file[:-1]+'c')
        f.write('CAPI=2:\n')

        coredata = {
            'name'  : vlnv,
            'filesets' : {'rtl' : {'files' : files}},
            'targets' : {'default' : {'filesets' : ['rtl']}}
            }
        f.write(yaml.dump(coredata))
exit(rc)
