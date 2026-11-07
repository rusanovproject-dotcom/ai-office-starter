"""Native event adapters. Their JSON output is context, not an enforcement claim."""
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from common import ROOT
from bootstrap import bootstrap
from state import focus
from router import route, hints

def handle(host,event,payload):
    cwd=Path(os.environ.get('OFFICE_TASK_CWD') or payload.get('cwd',str(ROOT))).resolve()
    if not cwd.is_relative_to(ROOT.resolve()):raise ValueError('Event cwd outside this office')
    if event=='SessionStart':
        context=bootstrap(ROOT,payload.get('session_id'))
    elif event=='UserPromptSubmit':
        context='[now] '+datetime.now().astimezone().isoformat()+'\n'+focus(ROOT)+'\n'+hints(route(ROOT,payload.get('prompt',''),cwd))
    else:raise ValueError('Unsupported lifecycle event')
    if host=='plain':return context
    return json.dumps({'hookSpecificOutput':{'hookEventName':event,'additionalContext':context}},ensure_ascii=False)

if __name__=='__main__':
    try:
        payload=json.load(sys.stdin)
        host=sys.argv[1] if len(sys.argv)>1 else 'plain'
        event=payload.get('hook_event_name',sys.argv[2] if len(sys.argv)>2 else 'SessionStart')
        print(handle(host,event,payload))
    except (ValueError, OSError, RuntimeError) as exc:
        print('BLOCKED:office-hook: '+str(exc),file=sys.stderr)
        raise SystemExit(1)
