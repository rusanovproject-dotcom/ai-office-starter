"""Local template update with hash-verified preservation, conflict refusal and rollback.

A backup contains the selected office tree, not just today's known data folders.
Only files named in a validated template ownership manifest may be updated.
"""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import shutil
import stat
from common import ROOT, atomic_write, digest, is_secret_path, lock, read_json, safe_path
from personalize import START, END, block
from registry import ROLE_WORDS, render_map, validate_registry
from materialize import materialize

METADATA = {'.office/template-manifest.json', '.office/skills-manifest.json', '.office/legacy-manifest.json', '.office/release-paths.json'}
SPECIAL = {'AGENTS.md', 'CLAUDE.md', 'team/registry.json', 'team/map.md', '.office/skills-manifest.json'}
SECRET = re.compile(r'(^|/)(\.env($|\.)|\.envrc$|secrets($|\.)|credentials($|\.)|config\.env$|id_(rsa|dsa|ecdsa|ed25519)|\.netrc$|\.pgpass$|service-account)|\.(pem|key|mp4|mov|mkv|webm|mp3|m4a|wav|ogg|oga|opus|aac|flac|pdf|png|jpe?g|heic)$', re.I)
EXCLUDED = {'.git', '__pycache__', 'node_modules', '.venv', 'dist', '.pytest_cache'}
OWNER_SECTION = re.compile(r'(## Кто владелец офиса[^\n]*\n)(.*?)(?=\n## |\Z)', re.S)


def _checked(root, rel):
    path = safe_path(root, rel)
    for component in (path, *path.parents):
        if component == root.parent:
            break
        if component.is_symlink():
            raise ValueError('Symlink запрещён в обновляемом дереве: ' + rel)
    return path


def _eligible(rel):
    parts = Path(rel).parts
    if any(part in EXCLUDED for part in parts) or SECRET.search(rel) or is_secret_path(rel):
        return False
    if parts[0] == '.office' and rel not in METADATA:
        return False
    return True


def _files(root):
    result = {}
    for path in root.rglob('*'):
        rel = path.relative_to(root).as_posix()
        if not _eligible(rel):
            continue
        if path.is_symlink():
            raise ValueError('Symlink не копируется: ' + rel)
        if path.is_file():
            _checked(root, rel)
            result[rel] = path
    return result


def _ownership(path):
    _checked(path.parents[1], path.relative_to(path.parents[1]).as_posix())
    data = read_json(path)
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('files'), dict):
        raise ValueError('Нет корректного ownership-манифеста: ' + str(path))
    for rel, sha in data['files'].items():
        if not isinstance(rel, str) or not _eligible(rel) or rel == '.office/template-manifest.json':
            raise ValueError('Недопустимый template-owned путь: ' + str(rel))
        safe_path(path.parents[1], rel)
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
            raise ValueError('Некорректный SHA256: ' + rel)
    return data


def _decode(path):
    raw = path.read_bytes()
    for encoding in ('utf-8', 'cp1251'):
        try:
            return raw.decode(encoding)
        except UnicodeError:
            pass
    raise ValueError('Не удалось прочитать инструкции: ' + str(path))


def _owner(root):
    agents = root / 'AGENTS.md'
    if agents.exists():
        return {'file': 'AGENTS.md', 'format': 'markers', 'text': block(_decode(agents))}
    claude = root / 'CLAUDE.md'
    if claude.exists():
        match = OWNER_SECTION.search(_decode(claude))
        if match:
            return {'file': 'CLAUDE.md', 'format': 'legacy', 'text': match[2]}
    return None


def _merge_owner(text, owner):
    block(text)
    if owner is None:
        return text
    return text.split(START)[0] + START + owner['text'] + END + text.split(END)[1]


def _backup_location(root, folder):
    root = root.resolve()
    folder = Path(folder).expanduser().absolute()
    if folder.is_symlink() or folder.resolve() == root or root.is_relative_to(folder.resolve()):
        raise ValueError('Небезопасный путь backup: ' + str(folder))
    if folder.resolve().is_relative_to(root) and not folder.resolve().is_relative_to(root / '.office/backups'):
        raise ValueError('Внутри офиса backup допустим только в .office/backups/')
    # Canonicalize OS aliases such as macOS /var -> /private/var. The backup
    # leaf and every copied content path are still forbidden from being symlinks.
    return folder.resolve()


def _legacy_baseline(root, candidate=None):
    paths = [root / '.office/legacy-manifest.json']
    if candidate is not None:
        paths.insert(0, candidate / '.office/legacy-manifest.json')
    for path in paths:
        if path.exists():
            return _ownership(path)
    return {'version': 1, 'files': {}}


def _save_manifest(folder, manifest):
    data = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')
    atomic_write(folder / 'manifest.json', data)
    atomic_write(folder / 'manifest.sha256', digest(data) + '\n')


def backup(root, folder, baseline=None):
    root = root.resolve()
    folder = _backup_location(root, folder)
    if folder.exists() and any(folder.iterdir()):
        raise ValueError('Backup-каталог не пуст')
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    files = _files(root)
    if baseline is None:
        path = root / '.office/template-manifest.json'
        baseline = _ownership(path) if path.exists() else _legacy_baseline(root)
    owned = baseline.get('files', {})
    owner = _owner(root)
    hashes, modes, owner_files = {}, {}, []
    for rel, path in files.items():
        data = path.read_bytes()
        hashes[rel] = digest(data)
        modes[rel] = stat.S_IMODE(path.stat().st_mode) & 0o777
        atomic_write(_checked(folder / 'files', rel), data)
        if owned.get(rel) != hashes[rel] and rel not in SPECIAL and rel not in METADATA:
            owner_files.append(rel)
    if owner:
        atomic_write(folder / 'owner-block.md', owner['text'])
        owner = {k: v for k, v in owner.items() if k != 'text'} | {'sha256': digest((folder / 'owner-block.md').read_bytes())}
    manifest = {'version': 1, 'kind': 'office-update-backup', 'root': str(root), 'files': hashes, 'modes': modes,
                'owner_files': sorted(owner_files), 'owner': owner, 'allowed_changes': {}, 'transaction': [],
                'registry_records': read_json(root / 'team/registry.json', {}).get('agents', [])}
    _save_manifest(folder, manifest)
    _read_backup(root, folder)
    return folder


def _read_backup(root, folder):
    folder = _backup_location(root, folder)
    _checked(folder, 'manifest.json')
    _checked(folder, 'manifest.sha256')
    receipt = folder / 'manifest.sha256'
    if not receipt.is_file() or digest((folder / 'manifest.json').read_bytes()) != receipt.read_text(encoding='ascii').strip():
        raise ValueError('Манифест backup повреждён')
    manifest = read_json(folder / 'manifest.json')
    if not isinstance(manifest, dict) or manifest.get('kind') != 'office-update-backup' or manifest.get('version') != 1 or manifest.get('root') != str(root.resolve()):
        raise ValueError('Backup не принадлежит этому офису')
    files = manifest.get('files')
    if not isinstance(files, dict) or not isinstance(manifest.get('owner_files'), list):
        raise ValueError('Повреждён манифест backup')
    for rel, sha in files.items():
        if not _eligible(rel):
            raise ValueError('Недопустимый файл backup')
        path = _checked(folder / 'files', rel)
        if not path.is_file() or digest(path.read_bytes()) != sha:
            raise ValueError('Backup повреждён: ' + rel)
    if any(rel not in files for rel in manifest['owner_files']):
        raise ValueError('Owner-манифест ссылается вне backup')
    owner = manifest.get('owner')
    if owner:
        path = folder / 'owner-block.md'
        if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != owner.get('sha256'):
            raise ValueError('Backup owner-блока повреждён')
    return manifest


def _backup_owner(folder, manifest):
    if not manifest.get('owner'):
        return None
    return {'text': (folder / 'owner-block.md').read_text(encoding='utf-8')}


def verify(root, folder, all_files=False):
    folder = Path(folder).absolute()
    manifest = _read_backup(root, folder)
    paths = manifest['files'] if all_files else manifest['owner_files']
    for rel in paths:
        expected = manifest.get('allowed_changes', {}).get(rel, manifest['files'][rel]) if not all_files else manifest['files'][rel]
        path = _checked(root, rel)
        if not path.is_file() or digest(path.read_bytes()) != expected:
            raise ValueError('Сохранность не подтверждена: ' + rel)
    previous_registry = manifest.get('registry_records', [])
    if previous_registry:
        validate_registry(root)
        actual = {item['id']: item for item in read_json(root / 'team/registry.json', {}).get('agents', [])}
        if any(actual.get(item['id']) != item for item in previous_registry):
            raise ValueError('Персональные записи реестра изменились при обновлении')
    owner = manifest.get('owner')
    if owner:
        current = _owner(root)
        if current is None or digest(current['text'].encode('utf-8')) != owner['sha256']:
            raise ValueError('Owner-блок не восстановлен буквально')
    return True


def _write(root, rel, data, mode=None):
    path = _checked(root, rel)
    atomic_write(path, data)
    if mode is not None:
        path.chmod(mode)


def restore(root, folder):
    folder = Path(folder).absolute()
    manifest = _read_backup(root, folder)
    for rel in manifest['owner_files']:
        _write(root, rel, _checked(folder / 'files', rel).read_bytes(), manifest.get('modes', {}).get(rel))
    if 'team/registry.json' in manifest['files']:
        for rel in ('team/registry.json', 'team/map.md'):
            if rel in manifest['files']:
                _write(root, rel, _checked(folder / 'files', rel).read_bytes(), manifest.get('modes', {}).get(rel))
    owner = _backup_owner(folder, manifest)
    if owner:
        if (root / 'AGENTS.md').exists():
            _write(root, 'AGENTS.md', _merge_owner(_decode(root / 'AGENTS.md'), owner))
        elif manifest['owner']['format'] == 'legacy':
            _write(root, 'CLAUDE.md', (folder / 'files/CLAUDE.md').read_bytes(), manifest.get('modes', {}).get('CLAUDE.md'))
        else:
            raise ValueError('Нет AGENTS.md для owner-блока; backup сохранён')
    # Explicit restore returns original owner files, not transformed expectations.
    manifest['allowed_changes'] = {}
    _save_manifest(folder, manifest)
    verify(root, folder)
    return True


def cleanup(root, folder):
    folder = _backup_location(root, folder)
    verify(root, folder)
    shutil.rmtree(folder)
    return True


def _preflight_generated(root):
    path = root / '.office/skills-manifest.json'
    if not path.exists():
        return
    manifest = read_json(path)
    for rel, sha in manifest.get('files', {}).items():
        current = _checked(root, rel)
        if current.exists() and digest(current.read_bytes()) != sha:
            raise ValueError('Конфликт изменённой производной копии: ' + rel)


def _owner_content(rel):
    path = Path(rel)
    if path.name in ('AGENTS.md', 'CLAUDE.md') or path.name.startswith('_'):
        return False
    if rel.startswith(('me/', 'work/', 'clients/', 'projects/', 'results/', 'knowledge/')):
        return True
    return rel.startswith('team/agents/') and (path.name in ('card.md', 'memory.md') or '/memory/' in rel or '/knowledge/' in rel)


def _legacy_owner_envelope(text):
    match = OWNER_SECTION.search(text)
    if not match:
        raise ValueError('В старом CLAUDE.md нет owner-секции')
    return text[:match.start(2)] + '<OWNER>' + text[match.end(2):]


def _legacy_goal(root):
    path = root / 'team/agents/atlas/card.md'
    if not path.exists() or (root / 'me/goals.md').exists():
        return {}
    text = _decode(path)
    match = re.search(r'^\s*(?:-\s*)?\*\*Вектор:\*\*\s*(.*?)\s*$', text, re.M)
    if not match or not match[1] or '<' in match[1] or 'me/goals.md' in match[1]:
        return {}
    literal = match[1]
    goal = {'id': 'legacy-atlas-vector', 'subject': 'owner', 'kind': 'intention', 'status': 'hypothesis',
            'value': literal, 'scope': 'legacy:unspecified', 'horizon': 'unknown', 'state': 'needs-confirmation',
            'source': 'team/agents/atlas/card.md (legacy literal, confirmation date unknown)', 'recorded_at': date.today().isoformat()}
    goal_text = '# Цели по областям\n\nИсходные слова сохранены буквально. Область, горизонт и текущую актуальность нужно подтвердить; дату подтверждения офис не выдумывает.\n\n```office-goals\n' + json.dumps([goal], ensure_ascii=False, indent=2) + '\n```\n'
    # Preserve the complete old card as history, not a competing current source.
    new_card = '# Перенесённая карточка коуча\n\nТекущие цели — `me/goals.md`, id `legacy-atlas-vector`. Старый текст ниже — история; он не отменяет последующих поправок.\n\n## Исторический исходник (буквально)\n\n' + text
    return {'me/goals.md': goal_text.encode('utf-8'), 'team/agents/atlas/card.md': new_card.encode('utf-8')}


def _merge_registry(root, candidate):
    new = read_json(candidate / 'team/registry.json')
    old = read_json(root / 'team/registry.json')
    if not old:
        return new
    # Existing entries retain all owner choices; genuinely new builtins may join.
    result = {'version': 1, 'agents': list(old['agents'])}
    ids = {item['id'] for item in result['agents']}
    result['agents'] += [item for item in new['agents'] if item['id'] not in ids]
    return result


def _legacy_registry(root, candidate):
    data = read_json(candidate / 'team/registry.json')
    map_path = root / 'team/map.md'
    rows = {}
    if map_path.exists():
        for line in _decode(map_path).splitlines():
            target = re.search(r'team/agents/([a-z0-9][a-z0-9_-]*)/(core|CLAUDE)\.md', line)
            if not target:
                continue
            slug = target[1]
            identity = re.search(r'^- \*\*([^*]+)\*\*\s*(?:\(([^)]*)\))?', line)
            if not identity or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
                raise ValueError('Неоднозначная строка legacy-карты: ' + slug)
            if slug in rows and rows[slug]['line'] != line.strip():
                raise ValueError('Конфликт нескольких строк legacy-сотрудника: ' + slug)
            aliases=[]
            for alias in (identity[2] or '').split(','):
                alias=alias.strip()
                if not alias or alias.casefold() in ROLE_WORDS:
                    continue
                if ' ' in alias or not alias[0].isupper() or not re.fullmatch(r'[\w-]{1,80}',alias):
                    raise ValueError('Уточни имя/роль в legacy-алиасе: ' + alias)
                aliases.append(alias)
            rows[slug]={'line':line.strip(),'name':identity[1].strip(),'aliases':aliases,'core':target[0]}
    known=set()
    for item in data['agents']:
        slug=item['id'];known.add(slug)
        row=rows.get(slug)
        if not row:continue
        if row['name']!=item['name']:
            row['aliases']=list(dict.fromkeys([*row['aliases'],item['name']]))
        item['name'],item['aliases']=row['name'],row['aliases']
        complete=all((root/rel).is_file() and (root/rel).stat().st_size for rel in [item['core'],item['card'],*item['memory']])
        if 'заглушка' not in row['line'] and complete:item['status']='active'
    for slug,row in rows.items():
        if slug in known:continue
        core=_checked(root,row['core'])
        if not core.is_file() or not _decode(core).strip():
            raise ValueError('Нет core пользовательского сотрудника: '+slug)
        folder=root/'team/agents'/slug
        memory=[]
        if (folder/'memory.md').is_file():memory.append('team/agents/'+slug+'/memory.md')
        if (folder/'memory').is_dir():
            memory += [p.relative_to(root).as_posix() for p in sorted((folder/'memory').rglob('*.md')) if p.is_file()]
        data['agents'].append({'id':slug,'name':row['name'],'aliases':row['aliases'],
            'role':'пользовательская роль из legacy-офиса','scope':['задачи из собственного core; уточнить при пробе'],
            'forbidden':['внешние действия без разрешения','непроверенная экспертность'],
            'core':row['core'],'card':'team/agents/'+slug+'/card.md',
            'memory':memory or ['team/agents/'+slug+'/memory.md'],'status':'draft'})
    return data


def apply_update(root, candidate, folder):
    root, candidate = root.resolve(), Path(candidate).resolve()
    if root == candidate or candidate.is_relative_to(root) or root.is_relative_to(candidate):
        raise ValueError('Кандидат обновления должен быть отдельной распакованной папкой')
    marker = read_json(_checked(candidate, '.office-template.json'))
    if marker != {'format': 1, 'name': 'ai-office-starter'}:
        raise ValueError('Кандидат не является поддерживаемым ai-office-starter')
    if (root / '.office-template.json').exists() and read_json(root / '.office-template.json') != marker:
        raise ValueError('Идентификатор текущего офиса не совпадает с кандидатом')
    with lock(root, 'update'):
        incoming = _ownership(candidate / '.office/template-manifest.json')
        for rel, sha in incoming['files'].items():
            path = _checked(candidate, rel)
            if not path.is_file() or digest(path.read_bytes()) != sha:
                raise ValueError('Кандидат не соответствует манифесту: ' + rel)
        current_manifest = root / '.office/template-manifest.json'
        legacy = not current_manifest.exists()
        baseline = _legacy_baseline(root, candidate) if legacy else _ownership(current_manifest)
        if legacy and not baseline['files']:
            raise ValueError('Для старого офиса нужен проверенный legacy ownership-манифест')
        folder = backup(root, folder, baseline)
        manifest = _read_backup(root, folder)
        owner = _backup_owner(folder, manifest)
        planned = {}
        try:
            _preflight_generated(root)
            if not legacy and (root / 'team/registry.json').exists():
                validate_registry(root)
            if legacy and (root / 'CLAUDE.md').exists():
                expected_envelope = baseline.get('claude_envelope')
                if not expected_envelope or digest(_legacy_owner_envelope(_decode(root / 'CLAUDE.md')).encode()) != expected_envelope:
                    raise ValueError('Изменены общие правила старого CLAUDE.md вне owner-секции; требуется явное разрешение конфликта')
            if not legacy and (root / 'CLAUDE.md').exists():
                sha = digest((root / 'CLAUDE.md').read_bytes())
                if sha not in (baseline['files'].get('CLAUDE.md'), incoming['files'].get('CLAUDE.md')):
                    raise ValueError('Изменена совместимая обёртка CLAUDE.md; требуется разрешить конфликт')
            # Detect every modified template file before the first mutation.
            for rel in set(incoming['files']) | set(baseline['files']):
                path = _checked(root, rel)
                if not path.exists() or rel in SPECIAL or rel in METADATA:
                    continue
                current = digest(path.read_bytes())
                old_hash = baseline['files'].get(rel)
                incoming_hash = incoming['files'].get(rel)
                if current != old_hash and current != incoming_hash:
                    # Personal forms, cards, memory, indexes and content belong to the owner.
                    # They are preserved; shared instructions/code/skills must be reconciled.
                    if rel in incoming['files'] and old_hash != incoming_hash and not _owner_content(rel):
                        raise ValueError('Конфликт пользовательской правки template-файла: ' + rel)
            if not legacy and (root / 'AGENTS.md').exists():
                before = _decode(root / 'AGENTS.md')
                # Baseline hashes alone cannot verify an edited envelope; its original bytes
                # are supplied with template-manifest metadata by the packager.
                expected = baseline.get('agents_envelope')
                if expected and digest(_merge_owner(before, {'text': '<OWNER>'}).encode()) != expected:
                    raise ValueError('Изменены общие инструкции AGENTS.md вне owner-блока')
                if not expected and digest(before.encode()) != baseline['files'].get('AGENTS.md'):
                    raise ValueError('Нет baseline envelope для изменённого AGENTS.md; требуется проверка конфликта')
            owner_files = set(manifest['owner_files'])
            for rel in incoming['files']:
                if rel in owner_files or rel in ('team/registry.json', 'team/map.md', '.office/skills-manifest.json'):
                    continue
                data = _checked(candidate, rel).read_bytes()
                if rel == 'AGENTS.md':
                    data = _merge_owner(data.decode('utf-8'), owner).encode('utf-8')
                planned[rel] = data
            for rel in baseline['files'].keys() - incoming['files'].keys():
                if rel in SPECIAL or rel in METADATA or rel in owner_files:
                    continue
                path = _checked(root, rel)
                if path.exists() and digest(path.read_bytes()) == baseline['files'][rel]:
                    planned[rel] = None
            registry = _legacy_registry(root, candidate) if legacy else _merge_registry(root, candidate)
            if registry:
                planned['team/registry.json'] = (json.dumps(registry, ensure_ascii=False, indent=2) + '\n').encode()
                planned['team/map.md'] = render_map(registry).encode()
            if legacy:
                planned.update(_legacy_goal(root))
                # Move custom Claude-only procedures into the shared discovery tree,
                # keeping their original bytes in both clients and in the backup.
                for rel, path in _files(root).items():
                    if not rel.startswith('.claude/skills/') or rel in baseline['files']:
                        continue
                    canonical_rel = '.agents/skills/' + rel[len('.claude/skills/'):]
                    destination = _checked(root, canonical_rel)
                    data = path.read_bytes()
                    if destination.exists() and destination.read_bytes() != data:
                        raise ValueError('Конфликт собственного навыка при миграции: ' + canonical_rel)
                    if canonical_rel in incoming['files'] and incoming['files'][canonical_rel] != digest(data):
                        raise ValueError('Пользовательский навык совпал с новым штатным: ' + canonical_rel)
                    planned[canonical_rel] = data
            # Plan materialization too, so every generated path is in the rollback ledger.
            canonical = {rel: path.read_bytes() for rel, path in _files(root).items() if rel.startswith('.agents/skills/')}
            for rel, data in planned.items():
                if rel.startswith('.agents/skills/'):
                    if data is None:
                        canonical.pop(rel, None)
                    else:
                        canonical[rel] = data
            generated = {}
            for rel, data in canonical.items():
                dst_rel = '.claude/skills/' + rel[len('.agents/skills/'):]
                dst = _checked(root, dst_rel)
                if dst.exists() and dst.read_bytes() != data:
                    previous = baseline['files'].get(dst_rel)
                    generated_meta = read_json(root / '.office/skills-manifest.json', {'files': {}})['files'].get(dst_rel)
                    if digest(dst.read_bytes()) not in (previous, generated_meta):
                        raise ValueError('Конфликт производного навыка: ' + dst_rel)
                planned[dst_rel] = data
                generated[dst_rel] = digest(data)
            planned['.office/skills-manifest.json'] = (json.dumps({'version': 1, 'files': generated}, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
            planned['.office/template-manifest.json'] = (json.dumps(incoming, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
            # Record deterministic transformed bytes before writing, while preserving the
            # original backup and its hashes for rollback and explicit restore.
            manifest['allowed_changes'] = {rel: digest(data) for rel, data in planned.items() if rel in owner_files and data is not None}
            manifest['transaction'] = sorted(planned)
            _save_manifest(folder, manifest)
            for rel, data in planned.items():
                if data is None:
                    _checked(root, rel).unlink(missing_ok=True)
                else:
                    mode = stat.S_IMODE(_checked(candidate, rel).stat().st_mode) & 0o777 if (candidate / rel).exists() else None
                    _write(root, rel, data, mode)
            if registry:
                validate_registry(root)
            materialize(root)
            verify(root, folder)
            return {'status': 'updated', 'backup': str(folder), 'legacy': legacy}
        except BaseException:
            # Roll back only this transaction's writes. Preserve unrelated owner edits.
            for rel in reversed(list(planned)):
                target = _checked(root, rel)
                if rel in manifest['files']:
                    _write(root, rel, _checked(folder / 'files', rel).read_bytes(), manifest.get('modes', {}).get(rel))
                else:
                    target.unlink(missing_ok=True)
            # materialize can add canonical custom skills to the Claude copy; restore its
            # manifest and remove only transaction-generated files that were not present.
            original_skills = manifest['files'].get('.office/skills-manifest.json')
            if original_skills:
                _write(root, '.office/skills-manifest.json', (folder / 'files/.office/skills-manifest.json').read_bytes())
            manifest['allowed_changes'] = {}
            manifest['result'] = 'rolled-back; backup retained'
            _save_manifest(folder, manifest)
            raise


def main():
    parser = argparse.ArgumentParser(description='Локальное обновление, без fetch/push и внешней отправки')
    parser.add_argument('command', choices=('backup', 'restore', 'owner-restore', 'verify', 'cleanup', 'apply'))
    parser.add_argument('directory', type=Path)
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'apply':
            if args.backup is None:
                parser.error('apply требует --backup DIR')
            result = apply_update(ROOT, args.directory, args.backup)
            print(json.dumps(result, ensure_ascii=False))
        else:
            function = {'backup': backup, 'restore': restore, 'owner-restore': restore, 'verify': verify, 'cleanup': cleanup}[args.command]
            function(ROOT, args.directory)
            print(args.command + '=ok')
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        parser.exit(1, args.command + '=BLOCKED: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
