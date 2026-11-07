"""One project creation path for onboarding and office-project-add."""
import argparse
import json
import re
from common import ROOT, atomic_write, lock, safe_path


def known_projects(root):
    result = []
    folder = root / 'projects'
    if not folder.exists(): return result
    for path in sorted(folder.iterdir()):
        if not path.is_dir() or path.name.startswith(('_', '.')): continue
        map_path = path / 'map.md'
        if not map_path.is_file(): continue
        text = map_path.read_text(encoding='utf-8')
        match = re.search(r'```office-project\s*\n(.*?)\n```', text, re.S)
        if match:
            data = json.loads(match.group(1))
            if data.get('slug') != path.name: raise ValueError('Slug не совпадает с папкой проекта')
        else:
            title = re.search(r'^# (?:Проект: )?(.+)$', text, re.M)
            data = {'slug': path.name, 'name': title.group(1).strip() if title else path.name, 'keywords': []}
        result.append(data)
    return result


def create_project(root, slug, name, purpose, acceptance, sources, access, keywords=None):
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        raise ValueError('Slug проекта: латиница, цифры и дефис')
    if not all(isinstance(v, str) and v.strip() for v in (name, purpose, acceptance)):
        raise ValueError('Нужны название, назначение и критерий результата')
    if not isinstance(sources, list) or not isinstance(access, list) or not sources or not access:
        raise ValueError('Укажи источники и допустимые действия проекта')
    if any(not isinstance(x, str) or not x.strip() for x in sources + access):
        raise ValueError('Пустой источник или доступ')
    path = safe_path(root, 'projects/' + slug)
    with lock(root, 'projects'):
        if path.exists():
            if not (path / 'map.md').is_file() or not (path / 'AGENTS.md').is_file() or not (path / 'CLAUDE.md').is_file():
                raise ValueError('Проект уже есть, но не полон; проверь его без перезаписи')
            return {'slug': slug, 'path': str(path), 'created': False}
        path.mkdir(parents=True)
        data = {'slug': slug, 'name': name, 'purpose': purpose, 'acceptance': acceptance, 'sources': sources, 'access': access, 'keywords': keywords or [name, slug]}
        files = {
            path / 'map.md': '# Проект: ' + name + '\n\n## Что это и зачем\n' + purpose + '\n\n## Цель\n' + acceptance + '\n\n## Статус\nНачат\n\n## Сделано и решения\nПроект создан локально.\n\n```office-project\n' + json.dumps(data, ensure_ascii=False, indent=2) + '\n```\n',
            path / 'AGENTS.md': '# Проект: ' + name + '\n\n## Предмет и границы\n' + purpose + '\n\n## Обязательные источники\n' + '\n'.join('- ' + s for s in sources) + '\n\n## Допустимые данные и действия\n' + '\n'.join('- ' + a for a in access) + '\nЭти уточнения не расширяют полномочия корневого офиса и хоста. Данные других клиентов не переносятся из примеров.\n\n## Результат и приёмка\n' + acceptance + '\nСохраняй результаты этого проекта в его папке; общий готовый материал можно связать ссылкой с results/.\n\n## Основной контекст\nНайди корень офиса по .office-template.json; перед работой прочитай его AGENTS.md и projects/AGENTS.md. Статус и решения — в map.md рядом. Полный профиль владельца сюда не копируй.\n',
            path / 'CLAUDE.md': '@AGENTS.md\n'
        }
        for relative, line in [('projects/map.md', f'- **{name}** — {purpose} · keywords: {", ".join(data["keywords"])} · → {slug}/map.md'), ('projects/INDEX.md', f'- [{name}]({slug}/)')]:
            p = root / relative
            previous = p.read_text(encoding='utf-8') if p.exists() else '# Проекты\n'
            files[p] = previous.rstrip() + '\n' + line + '\n'
        before = {p: p.read_bytes() if p.exists() else None for p in files}
        try:
            for p, value in files.items(): atomic_write(p, value)
        except BaseException:
            for p, value in before.items():
                if value is None: p.unlink(missing_ok=True)
                else: atomic_write(p, value)
            if not any(path.iterdir()): path.rmdir()
            raise
    return {'slug': slug, 'path': str(path), 'created': True}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('create',))
    for arg in ('slug','name','purpose','acceptance'):
        parser.add_argument('--' + arg, required=True)
    parser.add_argument('--sources', action='append', required=True)
    parser.add_argument('--access', action='append', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(create_project(ROOT, args.slug, args.name, args.purpose, args.acceptance, args.sources, args.access), ensure_ascii=False))
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, str(exc) + '\n')
