"""Local employee creation: draft files, real task evidence, owner confirmation."""
import argparse
from datetime import date
import json
import re
import sys
from common import ROOT, atomic_write, digest, is_secret_path, lock, safe_path
from registry import load_registry, save_registry


TEMPLATE_FOLDER = 'team/agents/demiurg/templates'
TEMPLATE_MARKER = re.compile(r'(?im)^#\s+(?:заготовка роли|шаблон роли|<имя>)|^>.*это шаблон')
PENDING_LINE = re.compile(r'\bTODO\b|\bTBD\b|^<[^>\n]+>$|^(?:заполнить|неизвестно|пока не знаю)$', re.I)


def evidence_file(root, relative):
    """Require an actual local text result, not an empty file or placeholder."""
    if not isinstance(relative, str) or not relative.strip() or is_secret_path(relative):
        raise ValueError('Нужен путь к разрешённому локальному документу')
    path = safe_path(root, relative)
    if not path.is_file():
        raise ValueError('Нет документа: ' + relative)
    content = path.read_text(encoding='utf-8')
    body = [line.strip() for line in content.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not body or all(PENDING_LINE.search(line) for line in body):
        raise ValueError('Нет содержательного документа: ' + relative)
    return digest(path.read_bytes())


def competence_sources(root, sources):
    substantive = False
    templates = (root / TEMPLATE_FOLDER).resolve()
    for source in sources:
        path = safe_path(root, source)
        evidence_file(root, source)
        if not path.resolve().is_relative_to(templates) and not TEMPLATE_MARKER.search(path.read_text(encoding='utf-8')):
            substantive = True
    if not substantive:
        raise ValueError('Шаблон роли не заменяет предметную методику и пример качества')


def probe_artifact(root, item, relative):
    if not isinstance(relative, str):
        raise ValueError('Нужен путь к результату пробы')
    path = safe_path(root, relative).resolve()
    parts = path.relative_to(root.resolve()).parts
    output_path = ((len(parts) >= 2 and parts[0] == 'results')
                   or (len(parts) >= 3 and parts[0] == 'projects'))
    forbidden = [item['core'], item['card'], *item['memory'], *item.get('sources', [])]
    if (not output_path or path.name in ('AGENTS.md', 'CLAUDE.md', 'INDEX.md')
            or any(path.resolve() == safe_path(root, source).resolve() for source in forbidden)):
        raise ValueError('Проба должна ссылаться на отдельный результат в results/ или projects/, а не на инструкции/источник')
    return evidence_file(root, relative)


def create_employee(root, spec):
    slug = spec.get('id', '')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        raise ValueError('Некорректный id сотрудника')
    for key in ('name', 'role', 'need', 'method', 'tone'):
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            raise ValueError('Нужно заполнить: ' + key)
    for key in ('aliases', 'scope', 'forbidden', 'sources', 'scenarios'):
        if not isinstance(spec.get(key), list) or any(not isinstance(v, str) or not v.strip() for v in spec[key]):
            raise ValueError('Некорректный список: ' + key)
        if key != 'aliases' and not spec[key]:
            raise ValueError('Нужно заполнить: ' + key)
    competence_sources(root, spec['sources'])
    competence = spec.get('competence', 'local')
    if competence not in ('local', 'expert'):
        raise ValueError('Уровень компетенции должен быть local или expert')
    if competence == 'local' and re.search(r'\b(?:эксперт\w*|expert\w*)', spec['role'], re.I):
        raise ValueError('Экспертная роль требует competence=expert и независимой проверки')
    folder = safe_path(root, 'team/agents/' + slug)
    with lock(root, 'employees'):
        data = load_registry(root)
        if any(a['id'] == slug for a in data['agents']) or folder.exists():
            raise ValueError('Сотрудник или его папка уже существует; не перезаписываю')
        item = {key: spec[key] for key in ('id', 'name', 'aliases', 'role', 'scope', 'forbidden')}
        item.update({'competence': competence, 'sources': list(spec['sources']), 'status': 'draft', 'core': f'team/agents/{slug}/core.md', 'card': f'team/agents/{slug}/card.md', 'memory': [f'team/agents/{slug}/memory.md']})
        core = '# ' + spec['name'] + '\n\n## Результат роли\n' + spec['need'] + '\n\n## Метод\n' + spec['method'] + '\n\n## Доступная методика\n' + '\n'.join('- ' + s for s in spec['sources']) + '\n\n## Область\n' + '\n'.join('- ' + s for s in spec['scope']) + '\n\n## Границы\n' + '\n'.join('- ' + s for s in spec['forbidden']) + '\nНе обещай недоступных инструментов и компетенций. Читай корневой AGENTS.md и только нужный предметный контекст. Предпочтения me/profile.md важнее голоса роли; роль и память не расширяют права. Пока status draft, не выдавай её за проверенного сотрудника.\n'
        card = '# Я — ' + spec['name'] + '\n\n**За что отвечаю:** ' + spec['role'] + '\n**Вектор:** согласованная задача: ' + spec['need'] + '; цели — me/goals.md, без копирования.\n**Помогаю с:** ' + '; '.join(spec['scenarios']) + '\n**Каким ты меня видишь:** ' + spec['tone'] + '; постоянные предпочтения — me/profile.md.\n**Источники:** ' + '; '.join(spec['sources']) + '\n**Границы:** ' + '; '.join(spec['forbidden']) + '\n**Статус:** draft, нужна пробная задача и подтверждение владельца.\n'
        files = {folder / 'core.md': core, folder / 'card.md': card, folder / 'memory.md': '# Память\n\n' + date.today().isoformat() + ' — создан черновик роли; личные сведения не копируются из профиля.\n'}
        try:
            for path, text in files.items(): atomic_write(path, text)
            data['agents'].append(item)
            save_registry(root, data)
        except BaseException:
            for path in files: path.unlink(missing_ok=True)
            if folder.exists() and not any(folder.iterdir()): folder.rmdir()
            raise
    return item


def activate_employee(root, slug, evidence):
    if evidence.get('confirmed') is not True:
        raise ValueError('Нет подтверждения владельцем результата пробной задачи')
    for key in ('task', 'output', 'artifact', 'criterion', 'assessment'):
        if not isinstance(evidence.get(key), str) or not evidence[key].strip():
            raise ValueError('Нужно evidence: ' + key)
    with lock(root, 'employees'):
        data = load_registry(root)
        item = next((a for a in data['agents'] if a['id'] == slug), None)
        if not item or item['status'] != 'draft':
            raise ValueError('Нет черновика для активации')
        from stage_check import slots, meaningful
        slots(root, item['card'])
        meaningful(safe_path(root, item['core']).read_text(encoding='utf-8'))
        for key in ('task', 'output', 'criterion', 'assessment'):
            meaningful(evidence[key])
        artifact_hash = probe_artifact(root, item, evidence['artifact'])
        if 'sources' in item:
            competence_sources(root, item['sources'])
        review_text = ''
        if item.get('competence', 'local') == 'expert':
            review = evidence.get('domain_review')
            if not isinstance(review, dict) or review.get('verdict') != 'pass':
                raise ValueError('Экспертной роли нужна независимая доменная оценка pass')
            reviewer = review.get('reviewer', '')
            if not isinstance(reviewer, str):
                raise ValueError('Не указан независимый проверяющий')
            meaningful(reviewer)
            if reviewer.strip().casefold() in {str(v).strip().casefold() for v in (slug, item['name'], *item['aliases'])}:
                raise ValueError('Роль не может независимо оценить сама себя')
            review_hash = probe_artifact(root, item, review.get('artifact'))
            if safe_path(root, review['artifact']).resolve() == safe_path(root, evidence['artifact']).resolve():
                raise ValueError('Независимая оценка должна иметь отдельный отчёт')
            review_text = '\nДоменный проверяющий: ' + reviewer + '\nОценка: pass; отчёт: ' + review['artifact'] + '; SHA256: ' + review_hash + '\n'
        card = safe_path(root, item['card'])
        memory = safe_path(root, item['memory'][0])
        originals = {card: card.read_bytes(), memory: memory.read_bytes()}
        text = '\n## Проверка роли\n' + date.today().isoformat() + '\nПробная задача: ' + evidence['task'] + '\nРезультат: ' + evidence['output'] + '\nАртефакт: ' + evidence['artifact'] + '; SHA256: ' + artifact_hash + '\nКритерий: ' + evidence['criterion'] + '\nОценка по критерию: ' + evidence['assessment'] + review_text + '\nПодтверждено владельцем. Эта запись не доказывает native subagent или доступ к внешнему инструменту.\n'
        try:
            atomic_write(card, card.read_text(encoding='utf-8').replace('**Статус:** draft, нужна пробная задача и подтверждение владельца.', '**Статус:** active, пробная задача подтверждена владельцем.') + text)
            atomic_write(memory, memory.read_text(encoding='utf-8') + text)
            item['status'] = 'active'
            save_registry(root, data)
        except BaseException:
            for path, value in originals.items(): atomic_write(path, value)
            raise
    return item

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='JSON ввод через stdin, без внешних отправок')
    parser.add_argument('command', choices=('create', 'activate'))
    parser.add_argument('--id')
    args = parser.parse_args()
    try:
        value = json.load(sys.stdin)
        if args.command == 'create': result = create_employee(ROOT, value)
        else:
            if not args.id: raise ValueError('Для activate нужен --id')
            result = activate_employee(ROOT, args.id, value)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, str(exc) + '\n')
