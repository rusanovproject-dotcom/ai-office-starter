"""Sequential local bootstrap: protection -> file snapshot -> state (no Git commits)."""
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from common import ROOT, atomic_write, digest, lock, read_json, write_json, is_secret_path
from state import continuation, focus, update

SIGNATURE = '# OFFICE-PD-GATE-v4'
SHIM = '''#!/bin/sh
# OFFICE-PD-GATE-v4
command -v python3 >/dev/null 2>&1 || { echo 'BLOCKED: Python missing, push not checked' >&2; exit 1; }
root=$(git rev-parse --show-toplevel) || exit 1
[ -f "$root/.office-template.json" ] || { echo 'BLOCKED: office root not found' >&2; exit 1; }
exec python3 "$root/scripts/office/privacy_gate.py" "$@"
'''

def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], text=True, capture_output=True, check=False)

def install_gate(root):
    if not shutil.which('git'): return 'BLOCKED:no-git'
    top=git(root,'rev-parse','--show-toplevel')
    if top.returncode: return 'SKIPPED:not-git'
    if Path(top.stdout.strip()).resolve()!=root.resolve(): return 'BLOCKED:foreign-repository'
    if not (root/'scripts/office/privacy_gate.py').is_file(): return 'BLOCKED:no-source'
    value=git(root,'rev-parse','--git-path','hooks')
    if value.returncode:return 'BLOCKED:hooks-path'
    hookdir=Path(value.stdout.strip()).expanduser()
    if not hookdir.is_absolute():hookdir=root/hookdir
    if not hookdir.resolve().is_relative_to(root.resolve()):return 'BLOCKED:hooks-external'
    dst=hookdir/'pre-push'
    if dst.is_symlink():return 'BLOCKED:foreign-pre-push'
    if dst.exists() and not dst.is_file():return 'BLOCKED:install-failed'
    if dst.exists():
        text=dst.read_text(encoding='utf-8',errors='replace')
        if SIGNATURE not in text and 'ПД-гейт офиса v3' not in text:return 'BLOCKED:foreign-pre-push'
    try:
        atomic_write(dst,SHIM)
        dst.chmod(0o700)
        return 'PASS' if dst.read_text()==SHIM and os.access(dst,os.X_OK) else 'BLOCKED:install-failed'
    except OSError:return 'BLOCKED:install-failed'

def snapshot(root):
    # Never stage/commit user WIP. Snapshot is private and excluded from packages/Git.
    folder=root/'.office/snapshots'/ (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8])
    if not folder.resolve().is_relative_to(root.resolve()):return 'BLOCKED:runtime-symlink'
    try:
        folder.mkdir(parents=True,mode=0o700)
        manifest={}
        for path in root.rglob('*'):
            rel=path.relative_to(root)
            if any(p in ('.git','.office','__pycache__','node_modules','.venv','dist') for p in rel.parts):continue
            if not path.is_file() or path.is_symlink():continue
            name=path.name.casefold()
            if is_secret_path(rel):continue
            if path.suffix.lower() in ('.pem','.key','.mp4','.mov','.mp3','.wav','.ogg','.pdf','.png','.jpg','.heic'):continue
            if path.stat().st_size>50*1024*1024:return 'BLOCKED:file-over-50MB'
            data=path.read_bytes()
            atomic_write(folder/rel,data)
            manifest[rel.as_posix()]=digest(data)
        write_json(folder/'manifest.json',manifest)
        return 'PASS:'+folder.name
    except OSError:return 'BLOCKED:snapshot-failed'

def bootstrap(root=ROOT, session_id=None):
    with lock(root,'bootstrap'):
        state=read_json(root/'.office/state.json',{})
        # Resume/compact gets fresh state; do not skip the gate check on a remembered session.
        protection=install_gate(root)
        snap=snapshot(root) if not session_id or state.get('snapshot_session')!=session_id else 'SKIPPED:same-session'
        changes={'pd_gate':protection,'last_bootstrap':datetime.now(timezone.utc).isoformat()}
        if session_id and snap.startswith('PASS:'):changes['snapshot_session']=session_id
        update(root,changes)
        context=''
        origin=os.environ.get('OFFICE_TASK_CWD')
        if origin:
            current=Path(origin).resolve()
            if current.is_relative_to(root.resolve()):
                from router import select_project
                project,_,_=select_project(root,'',current)
                if project:context='[launch-project] '+project['slug']+'; прочитай projects/'+project['slug']+'/AGENTS.md и map.md. Явный объект в просьбе имеет приоритет.'
        return '\n'.join(('[office-bootstrap] gate='+protection+' snapshot='+snap,context,continuation(root),focus(root)))

if __name__=='__main__':
    try:print(bootstrap())
    except (OSError,ValueError,RuntimeError) as exc:
        print('BLOCKED:bootstrap: '+str(exc))
        raise SystemExit(1)
