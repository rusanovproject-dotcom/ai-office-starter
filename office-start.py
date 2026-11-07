#!/usr/bin/env python3
"""Launch either client from this office's root, including a ZIP with no Git."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('client',choices=('codex','claude'))
parser.add_argument('--print-root',action='store_true')
args,remaining=parser.parse_known_args()
if not (root/'.office-template.json').is_file():parser.exit(1,'BLOCKED: office marker missing\n')
if args.print_root:
    print(root)
    raise SystemExit(0)
command=shutil.which(args.client)
if not command:parser.exit(1,'BLOCKED: client not installed: '+args.client+'\n')
origin=Path.cwd().resolve()
os.environ['OFFICE_TASK_CWD']=str(origin if origin.is_relative_to(root.resolve()) else root.resolve())
# Run explicit bootstrap even when hooks are untrusted/disabled. Not equivalent to hook trust.
subprocess.run([os.sys.executable,str(root/'scripts/office/bootstrap.py')],cwd=root,check=True)
os.chdir(root)
os.execv(command,[command,*(['-C',str(root)] if args.client=='codex' else []),*remaining])
