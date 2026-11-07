"""Fail-closed pre-push check over committed incoming history, never contacts a remote."""
import json
import re
import subprocess
import sys
from common import ROOT, digest

SECRET_NAME=re.compile(r'(^|/)(\.env($|\.)|\.envrc$|secrets($|[./])|credentials($|[./])|config\.env$|id_(rsa|dsa|ecdsa|ed25519)|\.netrc$|\.pgpass$|service-account)|\.(pem|key|mp4|mov|mkv|webm|mp3|m4a|wav|ogg|oga|aac|flac|opus|pdf|png|jpe?g|heic)$|transcript',re.I)
# Credential field context avoids treating manifest hashes, Git IDs and URLs as keys.
HEX_CREDENTIAL=re.compile(rb'''(?<![\w])(?:["']?(?:api[_-]?key|access[_-]?token|token|secret|password|key)["']?)\s*[:=]\s*["']?[0-9a-f]{32,}(?![\w])''',re.I)
TOKEN=re.compile(
    rb'(?<![\w/\-])(?:sk[-_]|gsk_|gh[pous]_)[A-Za-z0-9_-]{16,}|github_pat_[A-Za-z0-9_]{20,}'
    rb'|AKIA[0-9A-Z]{16}|AIza[A-Za-z0-9_-]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}'
    rb'|\d{8,10}:AA[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'
    rb'|eyJ[A-Za-z0-9_/+-]{15,}\.[A-Za-z0-9_/+-]{10,}'
    rb'|[A-Za-z][A-Za-z0-9+.-]*://[^\s/@]+:[^\s/@]{6,}@'
    rb'|hooks\.slack\.com/services/[A-Za-z0-9/]{20,}|api\.telegram\.org/bot[0-9]+:[A-Za-z0-9_-]+'
    rb'|[?&](?:api_?key|token|secret|access_token)=[A-Za-z0-9_.-]{16,}'
)


def run(root,*args):
    result=subprocess.run(['git','-C',str(root),*args],capture_output=True)
    if result.returncode:raise ValueError('Git history could not be verified')
    return result.stdout

def private_remote(url):
    # Only explicit GitHub PRIVATE from the exact host/repository counts. No push performed.
    match=re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?',url)
    if not match:return False
    try:
        result=subprocess.run(['gh','repo','view',match[1],'--json','visibility','--jq','.visibility'],capture_output=True,text=True,timeout=15)
        return result.returncode==0 and result.stdout.strip()=='PRIVATE'
    except (OSError,subprocess.TimeoutExpired):return False

def check(root,refs,url,private_check=private_remote):
    commits=set()
    for line in refs.splitlines():
        pieces=line.split()
        if len(pieces)!=4:raise ValueError('Malformed pre-push input')
        _,local,_,remote=pieces
        if not re.fullmatch('[0-9a-f]{40,64}',local) or not re.fullmatch('[0-9a-f]{40,64}',remote):raise ValueError('Invalid Git object')
        if set(local)=={'0'}:continue
        args=['rev-list',local]
        if set(remote)!={'0'}:args+=['^'+remote]
        commits.update(run(root,*args).decode().splitlines())
    has_owner=False
    for commit in commits:
        listing=run(root,'ls-tree','-r','-z',commit)
        entries={}
        for row in listing.split(b'\0'):
            if not row:continue
            meta,raw_path=row.split(b'\t',1)
            mode,kind,oid=meta.split()
            path=raw_path.decode('utf-8',errors='strict')
            if mode==b'120000':raise ValueError('Symlink in outgoing history')
            entries[path]=oid.decode()
        owned={}
        if '.office/template-manifest.json' in entries:
            data=json.loads(run(root,'cat-file','blob',entries['.office/template-manifest.json']))
            owned=data.get('files',{})
        for path,oid in entries.items():
            if SECRET_NAME.search(path):raise ValueError('Forbidden file type in outgoing history')
            data=run(root,'cat-file','blob',oid)
            if TOKEN.search(data) or HEX_CREDENTIAL.search(data):raise ValueError('Potential credential in outgoing history (value redacted)')
            personal = path.startswith(('me/','work/','clients/','inbox/','results/','projects/','knowledge/','team/ops/','team/agents/','.agents/skills/','.claude/skills/')) or path in ('AGENTS.md','CLAUDE.md','team/registry.json','team/map.md','MAP.md')
            if personal and owned.get(path)!=digest(data):
                has_owner=True
    if has_owner and not private_check(url):raise ValueError('Owner data requires verified PRIVATE remote; public/unknown blocked')
    return 'PASS:pre-push-history'

if __name__=='__main__':
    try:print(check(ROOT,sys.stdin.read(),sys.argv[2] if len(sys.argv)>2 else ''))
    except (OSError,ValueError,KeyError,UnicodeError) as exc:
        print('BLOCKED: '+str(exc),file=sys.stderr)
        raise SystemExit(1)
