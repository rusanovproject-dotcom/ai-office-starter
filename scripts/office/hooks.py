"""Fingerprint executable hook sources so new releases require a fresh native review."""
import hashlib
import json
from common import atomic_write, read_json

def bundle_digest(root):
    h=hashlib.sha256()
    for path in sorted((root/'scripts/office').glob('*')):
        if path.suffix not in ('.py','.sh'):continue
        h.update(path.name.encode()+b'\0'+path.read_bytes()+b'\0')
    return h.hexdigest()

def definitions(root,host):
    command='''bash -c 'd="$PWD"; while [ ! -f "$d/.office-template.json" ] && [ "$d" != / ]; do d="$(dirname "$d")"; done; [ -f "$d/.office-template.json" ] || { echo "BLOCKED: office root not found" >&2; exit 1; }; exec bash "$d/scripts/office/run.sh" adapter HOST' '''.strip().replace('HOST',host)
    command+=' # office-hook-bundle:'+bundle_digest(root)
    return {'SessionStart':[{'matcher':'startup|resume|clear|compact|fork','hooks':[{'type':'command','command':command,'timeout':30}]}],
            'UserPromptSubmit':[{'hooks':[{'type':'command','command':command,'timeout':30}]}]}

def generate(root,check=False):
    claude=root/'.claude/settings.json'
    settings=read_json(claude)
    expected=definitions(root,'claude')
    codex={'description':'Local office lifecycle. Review exact source definitions via /hooks; updates change the bundle fingerprint.','hooks':definitions(root,'codex')}
    if check:
        if settings.get('hooks')!=expected or read_json(root/'.codex/hooks.json')!=codex:
            raise ValueError('Hook definitions do not match executable sources; rebuild the clean template')
        return
    settings['hooks']=expected
    atomic_write(claude,json.dumps(settings,ensure_ascii=False,indent=2)+'\n')
    atomic_write(root/'.codex/hooks.json',json.dumps(codex,ensure_ascii=False,indent=2)+'\n')
