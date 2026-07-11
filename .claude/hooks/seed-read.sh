#!/usr/bin/env bash
# seed-read.sh — чтение seed анкеты (clients/<slug>/survey.json) по SEED-CONTRACT.
# Один исполняемый контракт: его зовут этапы стройки (stage-1 Шаг 0, stage-3) и его же
# гоняют тесты — инструкция и реальность не дрейфуют. Копия контракта с описанием значений
# лежит рядом со стройкой: .claude/skills/office-build/references/SEED-CONTRACT.md
#
# Выход (stdout, ключ=значение):
#   seed=ok + поля профиля и atlas_seed — файл есть, читается, хоть одно поле выжило;
#   seed=none — нет файла / битый JSON / нет python3 / НЕСКОЛЬКО анкет (не гадаем, чья) /
#               не выжило ни одного поля → офис тихо ведёт живой диалог с нуля.
# Гарантии: exit 0 всегда; traceback не летит; enum-поля строго по контракту (чужое или
# не-строка отбрасывается ТОЧЕЧНО, не убивая остальной seed); мусорный/усечённый
# atlas_vector не цитируется (строка не выводится).

{
  OFFICE_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
  cd "$OFFICE_ROOT" || { echo "seed=none"; exit 0; }
  command -v python3 >/dev/null 2>&1 || { echo "seed=none"; exit 0; }

  python3 - <<'PYEOF' 2>/dev/null || echo "seed=none"
import glob, json, sys

ENUMS = {
    'uroven_ai':     {'novichok', 'uverennyy', 'razrabotchik'},
    'atlas_preset':  {'myagkiy', 'pryamoy', 'analitik', 'situativnyy'},
    'atlas_focus':   {'sales_avoid', 'last_mile', 'shiny_new', 'perfectionism', 'avoid_scary', 'none'},
    'explain_level': {'terminal_pugaet', 'norm', 'razrabotchik'},
}
VECTOR_CAP = 200

def clean_text(v, cap):
    """Одна строка, без управляющих символов. Длиннее cap → None: дословно процитировать
    нельзя, а обрезок в кавычках («это твои слова») читается как чужие слова."""
    if not isinstance(v, str):
        return None
    v = ' '.join(v.split())
    v = ''.join(ch for ch in v if ch.isprintable())
    if not v or len(v) > cap:
        return None
    return v

def vector_ok(v):
    """Мусор не цитируем: вектору нужно >=2 слова и >=8 букв (эмодзи/«!!» не пройдут).
    Смысловой фильтр («ну не знаю, деньги наверное») — не здесь: его держит stage-3."""
    if not v:
        return False
    return len(v.split()) >= 2 and sum(ch.isalpha() for ch in v) >= 8

paths = sorted(glob.glob('clients/*/survey.json'))
# Несколько анкет — не гадаем, чья из них владельца (в clients/ живут и реальные клиенты,
# у психолога там могут появиться интейк-анкеты). Молча взять первую по алфавиту = риск
# процитировать КЛИЕНТА как владельца. Честный фолбэк на живой диалог.
if len(paths) != 1:
    print('seed=none'); sys.exit(0)

try:
    with open(paths[0], encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError
except Exception:
    print('seed=none'); sys.exit(0)

def sect(key):
    v = data.get(key)
    return v if isinstance(v, dict) else {}

meta, prof, seed = sect('meta'), sect('profile'), sect('atlas_seed')

fields = []
slug = clean_text(meta.get('slug'), 60)
if slug: fields.append(f'slug={slug}')
for key, src, cap in (('name', prof, 60), ('delo', prof, 120), ('nisha', prof, 120)):
    v = clean_text(src.get(key), cap)
    if v: fields.append(f'{key}={v}')
for key, src in (('uroven_ai', prof), ('atlas_preset', seed), ('atlas_focus', seed), ('explain_level', seed)):
    v = src.get(key)
    if isinstance(v, str) and v in ENUMS[key]:
        fields.append(f'{key}={v}')
vec = clean_text(seed.get('atlas_vector'), VECTOR_CAP)
if vector_ok(vec):
    fields.append(f'atlas_vector={vec}')

# Имени нет → подтверждать нечего, а stage-1 велит здороваться по имени: пустой seed=ok
# провоцирует галлюцинацию. Честнее живой диалог.
if not any(f.startswith('name=') for f in fields):
    print('seed=none'); sys.exit(0)

print('\n'.join(['seed=ok'] + fields))
PYEOF
  exit 0
} 2>/dev/null
