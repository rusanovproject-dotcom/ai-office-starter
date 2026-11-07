"""Canonical employee registry and deterministic human-readable map."""
import argparse
import json
import re
from common import ROOT, atomic_write, lock, read_json, safe_path

ROLE_WORDS = {'эксперт', 'консультант', 'коуч', 'стратег', 'хранительница', 'роутинг', 'оркестрация', 'найм', 'помощник'}

def load_registry(root):
    data = read_json(root / 'team/registry.json')
    if not isinstance(data, dict):
        raise ValueError('Нет корректного team/registry.json')
    return data

def render_map(data):
    lines = ['# Команда офиса', '', '> Производная карта из `team/registry.json`; вручную не редактировать. Роль в чате не означает запущенного subagent.', '']
    for item in data['agents']:
        aliases = ' · алиасы: ' + ', '.join(item['aliases']) if item['aliases'] else ''
        lines.append(f'- **{item["name"]}**{aliases} · роль: {item["role"]} · статус: {item["status"]} → {item["core"]}')
        lines.append('  Область: ' + '; '.join(item['scope']) + '. Запреты: ' + '; '.join(item['forbidden']) + '.')
    return '\n'.join(lines) + '\n'

def validate_registry(root, data=None, check_map=True):
    supplied = data is not None
    data = load_registry(root) if data is None else data
    if data.get('version') != 1 or not isinstance(data.get('agents'), list):
        raise ValueError('Неизвестная схема реестра')
    ids, names = set(), {}
    for item in data['agents']:
        slug = item.get('id', '')
        if not isinstance(slug, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug) or slug in ids:
            raise ValueError('Некорректный или повторяющийся id сотрудника')
        ids.add(slug)
        if item.get('status') not in ('active', 'draft'):
            raise ValueError('Статус сотрудника должен быть draft или active')
        for key in ('name', 'role', 'core', 'card'):
            if not isinstance(item.get(key), str) or not item[key].strip() or '\n' in item[key] or '\r' in item[key]:
                raise ValueError('Пустое/некорректное поле сотрудника: ' + key)
        for key in ('aliases', 'scope', 'forbidden', 'memory'):
            if not isinstance(item.get(key), list) or any(not isinstance(v, str) or not v.strip() or '\n' in v or '\r' in v for v in item[key]):
                raise ValueError('Некорректный список: ' + key)
        if not item['scope'] or not item['forbidden'] or not item['memory']:
            raise ValueError('Нужны область, запреты и путь памяти сотрудника')
        for name in [item['name'], *item['aliases']]:
            normalized = name.strip().casefold()
            if normalized in names:
                raise ValueError('Коллизия имени/алиаса: ' + name)
            names[normalized] = slug
        if any(a.casefold() in ROLE_WORDS for a in item['aliases']):
            raise ValueError('Алиас должен быть именем, а не ролью')
        for key in ('core', 'card'):
            path = safe_path(root, item[key])
            if not item[key].startswith('team/agents/' + slug + '/'):
                raise ValueError('Файлы сотрудника должны быть в его папке')
            if key == 'core' or item['status'] == 'active':
                if not path.is_file() or not path.read_text(encoding='utf-8').strip():
                    raise ValueError('Нет заполненного файла: ' + item[key])
        for rel in item['memory']:
            if not rel.startswith('team/agents/' + slug + '/'):
                raise ValueError('Память должна принадлежать папке сотрудника')
            path = safe_path(root, rel)
            if item['status'] == 'active' and (not path.is_file() or not path.read_text(encoding='utf-8').strip()):
                raise ValueError('Нет памяти активного сотрудника: ' + rel)
    if not supplied and check_map:
        path = root / 'team/map.md'
        if not path.exists() or path.read_text(encoding='utf-8') != render_map(data):
            raise ValueError('team/map.md расходится с реестром; запусти registry.py render')
    return data

def save_registry(root, data):
    validate_registry(root, data)
    with lock(root, 'registry'):
        paths = {root / 'team/registry.json': json.dumps(data, ensure_ascii=False, indent=2) + '\n', root / 'team/map.md': render_map(data)}
        old = {p: p.read_bytes() if p.exists() else None for p in paths}
        try:
            for path, text in paths.items(): atomic_write(path, text)
        except BaseException:
            for path, value in old.items():
                if value is None: path.unlink(missing_ok=True)
                else: atomic_write(path, value)
            raise
    return data

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('validate', 'render'))
    args = parser.parse_args()
    try:
        if args.command == 'render': save_registry(ROOT, load_registry(ROOT))
        else: validate_registry(ROOT)
        print('registry=ok')
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, str(exc) + '\n')
