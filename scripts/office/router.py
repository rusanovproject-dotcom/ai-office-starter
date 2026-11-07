"""Routing hints preserve project, named role and compatible skill intentions."""
import argparse
import json
from pathlib import Path
import re
from common import ROOT
from projects import known_projects
from registry import load_registry, validate_registry


def unquoted(text):
    return re.sub(r'«[^»]*»|“[^”]*”|"[^"\n]*"|`[^`]*`', ' ', text)


def outside_quotes(pattern, text):
    spans = [(m.start(), m.end()) for m in re.finditer(r'«[^»]*»|“[^”]*”|"[^"\n]*"|`[^`]*`', text)]
    return any(not any(start <= m.start() < end for start, end in spans) for m in re.finditer(pattern, text, re.I))


def keyword_hit(keyword, text):
    keyword = keyword.strip().casefold()
    stem = keyword.endswith('*')
    if stem: keyword = keyword[:-1]
    if len(keyword) < 3: return False
    return bool(re.search(r'(?<!\w)' + re.escape(keyword) + (r'\w*' if stem else r'(?!\w)'), text.casefold()))


def select_project(root, prompt, cwd=None):
    root = root.resolve()
    current = Path(cwd).resolve() if cwd else root
    if not current.is_relative_to(root):
        raise ValueError('Рабочий каталог вне выбранного офиса')
    projects = known_projects(root)
    # References never overrule an explicitly addressed target.
    target_text = re.split(r'\bкак\s+в\b|\bпо\s+примеру\b|\bобразец\b', prompt, maxsplit=1, flags=re.I)[0]
    explicit = []
    for project in projects:
        labels = [project['name'], project['slug']]
        if outside_quotes(r'(?<!\w)projects/' + re.escape(project['slug']) + r'(?:/|\b)', target_text):
            explicit.append(project); continue
        for label in labels:
            if outside_quotes(r'\b(?:для(?:\s+проекта)?|в\s+проекте|проект)\s+[«"“]?' + re.escape(label) + r'(?!\w)', target_text):
                explicit.append(project); break
    if len(explicit) == 1:
        return {**explicit[0], 'selection': 'explicit'}, [], False
    if len(explicit) > 1:
        return None, [p['slug'] for p in explicit], True
    relative = current.relative_to(root).parts
    if len(relative) >= 2 and relative[0] == 'projects':
        project = next((p for p in projects if p['slug'] == relative[1]), None)
        if project:
            return {**project, 'selection': 'cwd'}, [], False
    candidates = [p for p in projects if any(keyword_hit(k, unquoted(target_text)) for k in p.get('keywords', [p['name']]))]
    if len(candidates) == 1:
        return {**candidates[0], 'selection': 'candidate'}, [], False
    return None, [p['slug'] for p in candidates], len(candidates) > 1


def skill_matches(root, prompt):
    text = unquoted(prompt)
    result = []
    for path in sorted((root / '.agents/skills').glob('*/SKILL.md')):
        name = path.parent.name
        body = path.read_text(encoding='utf-8')
        explicit = re.search(r'(?<![\w-])[$/]?' + re.escape(name) + r'(?![\w-])', text, re.I)
        match = re.search(r'^\s+office-route:\s*(.+)$', body, re.M)
        keys = []
        if match:
            raw = match.group(1).strip().strip('"\'')
            keys = raw.partition('=>')[0].split('|')
        if explicit or any(keyword_hit(key, text) for key in keys):
            result.append(name)
    return result


def route(root, prompt, cwd=None):
    project, candidates, ambiguous = select_project(root, prompt, cwd)
    agent = None
    text = unquoted(prompt).strip()
    for item in validate_registry(root, load_registry(root))['agents']:
        for name in [item['name'], *item['aliases']]:
            if re.match(r'^@?' + re.escape(name) + r'(?:\s*[,!:]\s*|\s*$)', text, re.I):
                agent = dict(item)
                break
        if agent: break
    skills = skill_matches(root, prompt)
    return {'project': project, 'project_candidates': candidates, 'agent': agent, 'skills': skills,
            'needs_clarification': ambiguous,
            'note': 'Подсказка, не замена смыслового решения. Сохрани все совместимые результаты; уточняй объект, а не внутреннего исполнителя.'}


def hints(result):
    lines = []
    if result['project']:
        project = result['project']
        lines.append(f'[проект] {project["name"]} ({project["selection"]}): прочитай projects/{project["slug"]}/AGENTS.md и map.md. Референсы не переносят чужие факты.')
    elif result['needs_clarification']:
        lines.append('[проект] Уточни целевой объект: ' + ', '.join(result['project_candidates']))
    if result['agent']:
        agent = result['agent']
        if agent['status'] == 'active':
            lines.append(f'[агент] Явное обращение к {agent["name"]}: прочитай {agent["core"]}, {agent["card"]} и нужную память. Это роль в чате, не запуск subagent.')
        else:
            lines.append(f'[агент-черновик] {agent["name"]} ещё не активирован; не изображай проверенную роль. Ясную задачу выполни доступным способом.')
    if result['skills']:
        lines.append('[маршрут] Совместимые процедуры: ' + ', '.join(result['skills']) + '. Прочитай нужные .agents/skills/<name>/SKILL.md; имя сотрудника не отменяет процедуру.')
    return '\n'.join(lines)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('prompt')
    parser.add_argument('--cwd', type=Path)
    parser.add_argument('--hints', action='store_true')
    args = parser.parse_args()
    try:
        result = route(ROOT, args.prompt, args.cwd)
        print(hints(result) if args.hints else json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + '\n')
