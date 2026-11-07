"""Export only a frozen clean template. No Git, secrets, user data or runtime logs."""
import argparse
import io
from pathlib import Path
import zipfile
from common import ROOT, atomic_write, digest, is_secret_path, read_json, safe_path
from hooks import generate
from manifest import build_manifest
from materialize import materialize
from registry import validate_registry

REQUIRED={'AGENTS.md','CLAUDE.md','.office-template.json','.claude/settings.json','.codex/config.toml','.codex/hooks.json',
          '.agents/skills/office-build/SKILL.md','.claude/skills/office-build/SKILL.md','scripts/office/bootstrap.py','office-start.py'}
REQUIRED_CHECKS={'unit_tests','codex_runtime','package_extraction','independent_review','clone_smoke'}

def package(root,output,candidate=False,acceptance_report=None):
    root=root.resolve();output=Path(output).absolute()
    manifest=read_json(root/'.office/template-manifest.json')
    if not manifest or manifest!=build_manifest(root):raise ValueError('Манифест поставки отсутствует или устарел')
    files=manifest['files']
    required=REQUIRED|{domain+'/AGENTS.md' for domain in ('me','work','clients','projects','knowledge','inbox','results')}
    if not required<=files.keys():raise ValueError('Пропущены обязательные файлы поставки: '+', '.join(sorted(required-files.keys())))
    if 'Владелец пока не представлен.' not in (root/'AGENTS.md').read_text(encoding='utf-8'):
        raise ValueError('Это персонализированный офис, не чистый шаблон')
    for directory in ('me','work','clients','projects','results','knowledge','.agents/skills','.claude/skills','team/agents','scripts/office'):
        for path in (root/directory).rglob('*'):
            rel=path.relative_to(root)
            if '__pycache__' in rel.parts or path.name=='.DS_Store':continue
            if path.is_symlink():raise ValueError('Symlink в дереве поставки: '+str(rel))
            if path.is_file() and rel.as_posix() not in files and not is_secret_path(rel):
                raise ValueError('Есть владельческий или неописанный файл: '+str(rel))
    for rel in files:
        if is_secret_path(rel) or any(p in ('.git','tests','docs','snapshots','backups') for p in Path(rel).parts):
            raise ValueError('Частный/служебный путь в поставке: '+rel)
        path=safe_path(root,rel)
        if any(p.is_symlink() for p in (path,*path.parents) if p!=root.parent):
            raise ValueError('Symlink-зависимость поставки: '+rel)
    generate(root,check=True)
    materialize(root,check=True)
    validate_registry(root)
    if not candidate:
        report=read_json(Path(acceptance_report)) if acceptance_report else None
        if not report or report.get('overall') not in ('PASS','PASS_WITH_SKIPS') or report.get('blockers'):
            raise ValueError('Для ZIP выдачи нужен завершённый локальный отчёт приёмки')
        if report.get('source_manifest_sha256')!=digest((root/'.office/template-manifest.json').read_bytes()):
            raise ValueError('Отчёт относится к другой версии шаблона')
        checks={item['name']:item['status'] for item in report.get('checks',[])}
        if any(checks.get(name)!='PASS' for name in REQUIRED_CHECKS) or any(status not in ('PASS','SKIPPED') for status in checks.values()):
            raise ValueError('Обязательная локальная приёмка не пройдена')
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for rel in sorted([*files,'.office/template-manifest.json']):
            info=zipfile.ZipInfo('ai-office-starter/'+rel,date_time=(2026,11,7,0,0,0))
            info.external_attr=0o100644<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,safe_path(root,rel).read_bytes())
    data=stream.getvalue()
    if output.is_symlink() or (output.exists() and output.read_bytes()!=data):
        raise ValueError('Выход уже существует или является symlink; выбери новый путь')
    atomic_write(output,data)
    return {'path':str(output),'sha256':digest(data),'files':len(files)+1,'candidate':candidate}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Локальный ZIP чистого стартового шаблона')
    parser.add_argument('output',type=Path)
    parser.add_argument('--candidate',action='store_true',help='Тестовая упаковка; не выдаётся за пройденную приёмку')
    parser.add_argument('--acceptance-report',type=Path)
    args=parser.parse_args()
    try:print(package(ROOT,args.output,args.candidate,args.acceptance_report))
    except (OSError,ValueError,RuntimeError) as exc:parser.exit(1,'package=BLOCKED: '+str(exc)+'\n')
