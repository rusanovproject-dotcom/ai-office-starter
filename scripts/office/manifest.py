"""Developer-only template ownership manifest. Packaging verifies, never refreshes it."""
import argparse
from common import ROOT, digest, read_json, safe_path, write_json
from personalize import START, END, block
from hooks import generate

def build_manifest(root):
    spec=read_json(root/'.office/release-paths.json')
    if not isinstance(spec,dict) or spec.get('version')!=1 or not isinstance(spec.get('paths'),list):
        raise ValueError('Нет явного списка файлов поставки')
    files={}
    for relative in spec['paths']:
        path=safe_path(root,relative)
        if not path.is_file() or path.is_symlink():raise ValueError('Нет обычного файла поставки: '+relative)
        files[relative]=digest(path.read_bytes())
    agents=(root/'AGENTS.md').read_text(encoding='utf-8')
    block(agents)
    envelope=agents.split(START)[0]+START+'<OWNER>'+END+agents.split(END)[1]
    return {'version':1,'files':files,'agents_envelope':digest(envelope.encode('utf-8'))}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Для авторинга чистого шаблона, не обновления офиса владельца')
    parser.add_argument('--refresh',action='store_true')
    args=parser.parse_args()
    try:
        generate(ROOT,check=not args.refresh)
        current=build_manifest(ROOT)
        if args.refresh:write_json(ROOT/'.office/template-manifest.json',current)
        elif read_json(ROOT/'.office/template-manifest.json')!=current:raise ValueError('Template manifest drift')
        print('template-manifest=ok')
    except (ValueError,OSError) as exc:parser.exit(1,str(exc)+'\n')
