"""One canonical profile; regenerate only the marked owner block and summary."""
import argparse
from datetime import date
import json
import re
import sys
from common import ROOT, atomic_write, lock

START, END = '<!-- owner:start -->', '<!-- owner:end -->'
BUCKETS = {'work': ('work/map.md', 'office-facts'), 'goals': ('me/goals.md', 'office-goals')}

def block(text):
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        raise ValueError('Повреждены маркеры владельца AGENTS.md; автоматическая перезапись запрещена')
    return text.split(START)[1].split(END)[0]

def read_embedded(path, tag):
    if not path.exists():
        return None
    found = re.findall(r'```' + re.escape(tag) + r'\s*\n(.*?)\n```', path.read_text(encoding='utf-8'), re.S)
    if len(found) != 1:
        raise ValueError('Нет единственного блока ' + tag + ' в ' + str(path))
    return json.loads(found[0])

def embedded(title, tag, data):
    return title + '\n\n```' + tag + '\n' + json.dumps(data, ensure_ascii=False, indent=2) + '\n```\n'

def validate_record(record):
    if not isinstance(record, dict):
        raise ValueError('Запись должна быть объектом')
    for key in ('id', 'subject', 'kind', 'status'):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError('Запись без ' + key)
    if record['kind'] not in ('fact', 'intention', 'preference', 'hypothesis'):
        raise ValueError('Неизвестный тип записи')
    if record['status'] not in ('confirmed', 'hypothesis', 'unknown', 'undecided'):
        raise ValueError('Неизвестный статус записи')
    if record['status'] == 'confirmed':
        if not all(isinstance(record.get(k), str) and record[k].strip() for k in ('value', 'source', 'confirmed_at')):
            raise ValueError('Подтверждение требует значения, источника и даты')
        date.fromisoformat(record['confirmed_at'])

def render(profile):
    if not isinstance(profile, dict) or profile.get('version') != 1 or any(not isinstance(profile.get(k), list) for k in ('facts', 'rules', 'boundaries')):
        raise ValueError('Неизвестная схема профиля')
    facts = profile.get('facts', [])
    ids = {}
    for fact in facts:
        validate_record(fact)
        if fact['subject'] != 'owner':
            raise ValueError('Чужие факты не относятся к профилю владельца')
        if fact['id'] in ids:
            raise ValueError('Повтор id в профиле')
        ids[fact['id']] = fact
    lines = ['Подтверждённый профиль: `me/profile.md`. Персональные правила не расширяют полномочия.']
    for key in ('name', 'context'):
        fact = ids.get(key)
        if fact and fact['status'] == 'confirmed' and fact['kind'] == 'fact':
            lines.append(f'- {key}: {fact["value"]}')
    for rule in profile.get('rules', []):
        fact = ids.get(rule.get('basis'))
        if not fact or fact['status'] != 'confirmed' or fact['kind'] != 'preference':
            raise ValueError('Правило требует подтверждённого предпочтения-основания')
        if not all(isinstance(rule.get(k), str) and rule[k].strip() for k in ('action', 'scope', 'exception')):
            raise ValueError('Правило требует действия, области и исключения')
        lines.append(f'- Основание ({fact["id"]}): {fact["value"]}. Действие: {rule["action"]}. Область: {rule["scope"]}. Исключение: {rule["exception"]}.')
    for boundary in profile.get('boundaries', []):
        if not isinstance(boundary, dict) or set(boundary) != {'topic', 'status'} or not isinstance(boundary['topic'], str) or not boundary['topic'].strip() or boundary['status'] not in ('declined', 'undecided'):
            raise ValueError('Граница хранит только разрешённую тему и статус, без личного ответа')
        if boundary['status'] == 'declined':
            lines.append('- Не возвращайся без инициативы владельца к теме: ' + boundary['topic'] + '.')
    return '\n'.join(lines) + '\n'

def transaction(root, changes):
    for path in changes:
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Выход через symlink за пределы офиса запрещён')
    before = {p: p.read_bytes() if p.exists() else None for p in changes}
    try:
        for path, text in changes.items():
            atomic_write(path, text)
    except BaseException:
        for path, data in before.items():
            if data is None: path.unlink(missing_ok=True)
            else: atomic_write(path, data)
        raise

def summary(root):
    # Sources and ownership, never independently maintained prices/goals.
    return '# Выжимка офиса\n\nПерсональные рабочие правила — в AGENTS.md, полный подтверждённый профиль — [профиль](../me/profile.md).\nТекущие факты дела — [карта](../work/map.md), цели по областям — [цели](../me/goals.md).\nЖурнал знакомства — история, не источник текущих цен и целей.\n'

def save_profile(root, profile):
    owner = render(profile)
    with lock(root, 'profile'):
        path = root / 'AGENTS.md'
        text = path.read_text(encoding='utf-8')
        block(text)
        text = text.split(START)[0] + START + '\n' + owner + END + text.split(END)[1]
        block(text)  # Reject delimiters introduced by owner data before any writes.
        if len(text.encode('utf-8')) + ((root / 'CLAUDE.md').stat().st_size if (root / 'CLAUDE.md').exists() else 0) > 12 * 1024:
            raise ValueError('Корень превысил бюджет 12 KiB; сократи персональный блок')
        changes = {root / 'me/profile.md': embedded('# Подтверждённый профиль\n\n**Ядро собрано:** да', 'office-profile', profile), path: text,
                   root / 'knowledge/summary.md': summary(root)}
        index = root / 'knowledge/INDEX.md'
        index_text = index.read_text(encoding='utf-8') if index.exists() else '# Знания\n'
        if 'summary.md' not in index_text:
            changes[index] = index_text.rstrip() + '\n- [Выжимка](summary.md)\n'
        transaction(root, changes)

def load_records(root, bucket):
    path, tag = BUCKETS[bucket]
    return read_embedded(root / path, tag) or []

def save_records(root, bucket, records, imported=False):
    path, tag = BUCKETS[bucket]
    for record in records:
        validate_record(record)
        if bucket == 'goals' and not all(record.get(k) for k in ('scope', 'horizon', 'state')):
            raise ValueError('Цели требуют область, горизонт и состояние')
    with lock(root, 'facts'):
        current = {r['id']: r for r in load_records(root, bucket)}
        for record in records:
            old = current.get(record['id'])
            if imported and old:
                if record.get('confirmed_at', '') <= old.get('confirmed_at', ''):
                    continue
                if old['status'] == 'confirmed' and old.get('value') != record.get('value'):
                    raise ValueError('Импорт противоречит подтверждённому факту; уточни у владельца')
            current[record['id']] = record
        p = root / path
        title = '# Цели по областям' if bucket == 'goals' else '# Карта дела\n\n## Текущие подтверждённые факты\n\n## Источники и изменения'
        transaction(root, {p: embedded(title, tag, list(current.values())), root / 'knowledge/summary.md': summary(root)})

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='JSON ввод через stdin, без временного файла с личными ответами')
    parser.add_argument('bucket', choices=('profile', 'work', 'goals'))
    parser.add_argument('--imported', action='store_true')
    args = parser.parse_args()
    try:
        data = json.load(sys.stdin)
        if args.bucket == 'profile': save_profile(ROOT, data)
        else: save_records(ROOT, args.bucket, data, args.imported)
        print('personalization=ok')
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, str(exc) + '\n')
