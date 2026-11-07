"""Atomic state merges and timezone-aware daily focus."""
from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from common import lock, read_json, write_json

def update(root, changes):
    with lock(root, 'state'):
        path = root / '.office/state.json'
        current = read_json(path, {})
        current.update(changes)
        write_json(path, current)
        return current

def focus(root, now=None):
    path = root / 'team/ops/today.md'
    if not path.exists(): return ''
    text = path.read_text(encoding='utf-8')
    fields = dict(re.findall(r'^([^:\n]+):[ \t]*(.*)$', text, re.M))
    try:
        tz = ZoneInfo(fields['Timezone'].strip())
        current = (now or datetime.now(timezone.utc)).astimezone(tz)
        day = datetime.strptime(fields['Дата'].strip(), '%Y-%m-%d').date()
        if day.isoformat() != fields['Дата'].strip() or day != current.date(): return '[focus-status] SKIPPED: stale/future date'
    except (KeyError, ValueError, ZoneInfoNotFoundError):
        return '[focus-status] SKIPPED: invalid date/timezone'
    if fields.get('Режим', '').strip().casefold() == 'тишина': return '[focus-status] silence until end of this local day'
    mit = fields.get('MIT', '').split('<!--')[0].strip()
    if not mit: return ''
    return '[focus] MIT: ' + mit + (' · План: ' + fields['План'] if fields.get('План') else '')

def continuation(root):
    path = root / 'team/ops/build-log.md'
    if not path.exists(): return '[start] Новый офис: office-build, если нет ясной рабочей задачи.'
    states = {}
    for number, title, status in re.findall(r'^\s*#*\s*Этап (\d+):\s*(.*?)\s*\((открыт|готов|пропущен)\)',path.read_text(encoding='utf-8'),re.M):
        states[int(number)] = (title, status)
    opened = [(n,t) for n,(t,s) in states.items() if s=='открыт']
    if opened:
        n,title=sorted(opened)[0]
        return f'[continue] Открыт этап {n}: {title}. Продолжай по журналу, рабочая задача приоритетнее.'
    threads=root/'team/ops/threads.md'
    if threads.exists():
        return '[continue] Есть нити team/ops/threads.md; прочитай нужную по задаче.'
    return '[continue] Журнал есть; этапы и пробелы читай по задаче, знакомство не повторяй.'
