#!/bin/bash
# prompt-inject.sh — ЕДИНСТВЕННЫЙ UserPromptSubmit-инжект офиса v3 (второй не заводить).
# Инжектит: [now] реальное время + [focus] шапка дня (team/ops/today.md, есть с этапа 6)
# + ДЕТЕРМИНИРОВАННЫЙ РОУТЕР (3 прохода): имя агента → персона (team/map.md, со сверкой
# заглушки) · интент → скилл (ключи из route: каждого скилла, самопополняемо) · проект по
# keywords (projects/map.md). Мягкая деградация ВСЕХ веток: нет файла / нет совпадения →
# ветка молчит (модель/Директор решают сами). Каждый блок ≤3 строк — намёк, не лекция.
# Роутер даёт НАМЁК, не жёсткий диспатч: последнее слово за моделью, но горячий путь
# детерминирован (не «на удачу»). Источник ключей — сами скиллы (route:), не хардкод в хуке.

OFFICE_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$OFFICE_ROOT" || exit 0

# ── промпт пользователя из stdin (JSON) — python3, фолбэк: пусто ─────────────
PROMPT=""
if command -v python3 >/dev/null 2>&1; then
  PROMPT=$(python3 -c "import sys,json
try: print(json.load(sys.stdin).get('prompt',''))
except Exception: pass" 2>/dev/null)
fi

# ── [now] — реальное время (модель не угадывает «утро/ночь» по старому контексту)
echo "[now] $(date '+%Y-%m-%d %H:%M (%a)') — реальное текущее время, авторитетно."

# ── [focus] — шапка дня из team/ops/today.md (появляется на этапе 6) ─────────
TODAY="team/ops/today.md"
if [ -f "$TODAY" ]; then
  # Детект режима тишины БЕЗ bracket-классов [Рр]/[Тт] (под GNU grep/LC_ALL=C они матчат байт
  # и рвут многобайтовую кириллицу). «ишина» ищем ТОЛЬКО на строке с «ежим» (= «Режим: тишина»),
  # чтобы «режим сна» + случайное слово в другом месте файла не глушили день ложно.
  if grep 'ежим' "$TODAY" 2>/dev/null | grep -qF 'ишина'; then
    : # режим тишины — [focus]-сигналы глушатся до конца дня
  else
    mit=$(grep -m1 "^MIT:" "$TODAY" 2>/dev/null | sed 's/<!--.*-->//' | sed 's/[[:space:]]*$//')
    mit_value=$(printf '%s' "$mit" | sed 's/^MIT:[[:space:]]*//')
    if [ -n "$mit_value" ]; then
      plan=$(grep -m1 "^План:" "$TODAY" 2>/dev/null | sed 's/<!--.*-->//' | sed 's/[[:space:]]*$//')
      echo "[focus] $mit ${plan:+· $plan}"
    fi
  fi
fi
# нет today.md → ветка молчит (контур дня появится на этапе 6 — заговорит)

# ── ДЕТЕРМИНИРОВАННЫЙ РОУТЕР (python3: кириллица ломает байтовые cut/tr в BSD;
#    нет python3 → детекты молчат, [now]/[focus] живут).
#    3 прохода: (1) имя агента → персона (со сверкой заглушки); (2) интент → скилл
#    (ключи из route: каждого скилла — самопополняемо: новый скилл с route: = новый маршрут);
#    (3) проект по keywords. Всё — НАМЁК модели, не жёсткий диспатч; арбитраж при 2+ совпадениях.
if [ -n "$PROMPT" ] && command -v python3 >/dev/null 2>&1; then
  PROMPT="$PROMPT" python3 - <<'PYEOF'
import os, re, glob

prompt = os.environ.get('PROMPT', '')
lc = prompt.lower()
head = lc.strip()[:80]  # начало фразы — зона вызова по имени

name_hit_real = False   # True ТОЛЬКО для живого агента → тогда интент не роутим (юзер явно позвал персону)

def hit_kw(key, text):
    # совпадение по ГРАНИЦЕ СЛОВА (в py3 \w включает кириллицу): «сделай пост» НЕ ловит
    # «сделай поставку», «бот» НЕ ловит «поработай». Ключи короче 3 символов игнорируем.
    # Ключ с хвостовой * — СТЕМ: матчит словоформы по префиксу последнего слова
    # («отметь галочк*» ловит «отметь галочки/галочку»). Без * — только целое слово.
    stem = key.endswith('*')
    if stem:
        key = key[:-1].rstrip()
    if len(key) < 3:
        return False
    tail = r'\w*' if stem else r'(?!\w)'
    return re.search(r'(?<!\w)' + re.escape(key) + tail, text) is not None

# --- ПРОХОД 1: агент по имени из карты команды (team/map.md) ---
# Формат строки карты: «- **Имя** (алиасы) — роль … [заглушка …] → team/agents/<slug>/core.md»
# Скобки-алиасы стоят ПОСЛЕ **жирного имени**, поэтому паттерн ловит их за `**…**`, не внутри.
try:
    cards = open('team/map.md', encoding='utf-8').read()
    for m in re.finditer(r'^- \*\*([^*]+?)\*\*\s*(?:\(([^)]*)\))?[^\n]*', cards, re.M):
        block = m.group(0)
        names = [m.group(1).strip().lower()]
        if m.group(2):
            names += [a.strip().lower() for a in m.group(2).split(',')]

        def called(n):
            for cand in (n, '@' + n):
                if head == cand:
                    return True
                if head.startswith(cand) and len(head) > len(cand) and not head[len(cand)].isalpha():
                    return True
            return False

        hit = next((n for n in names if n and called(n)), None)
        if hit:
            nm = m.group(1).strip()
            if 'заглушка' in block.lower():
                # агент ещё не собран — НЕ отыгрывать. Но name_hit_real НЕ ставим: если рядом
                # боевая фраза («Атлас, набросай пост») — проход 2 должен отработать (рефлекс №5).
                print(f'[агент-заглушка] «{nm}» ещё не собран (появится на своём этапе). Честно скажи «на подходе», НЕ отыгрывай личность.')
            else:
                name_hit_real = True
                f = re.search(r'team/agents/[a-z0-9_-]+/(?:core|CLAUDE)\.md', block)
                path = f.group(0) if f else 'его core.md'
                print(f'[агент] Это вызов агента «{nm}» — прочитай {path} (+его card.md и память рядом: имя и характер могли выбрать заново) ПЕРЕД первым ответом от его лица.')
            break
except OSError:
    pass

# --- ПРОХОД 2: интент → скилл (детерминированно, ключи из route: каждого скилла) ---
# Пропускаем, только если юзер явно позвал ЖИВОГО агента. Заглушка+боевая фраза → интент работает.
if not name_hit_real:
    matches = []   # (skill_name, hint)
    for sk in glob.glob('.claude/skills/*/SKILL.md'):
        try:
            txt = open(sk, encoding='utf-8').read()
        except OSError:
            continue
        rm = re.search(r'^route:\s*(.+)$', txt, re.M)
        if not rm:
            continue
        val = rm.group(1).strip()
        if val[:1] in '"\'' and val[-1:] == val[:1]:   # снять кавычки-обёртку
            val = val[1:-1]
        keys_part, sep, hint = val.partition('=>')
        if not sep:                                    # нет '=>' → срезать хвостовой inline-комментарий
            keys_part = re.sub(r'\s+#.*$', '', keys_part)
        keys = [k.strip().lower() for k in keys_part.split('|') if k.strip()]
        skill_name = os.path.basename(os.path.dirname(sk))
        if any(hit_kw(k, lc) for k in keys):
            matches.append((skill_name, hint.strip() or skill_name))
    # дедуп по имени скилла
    seen = {}
    for sn, h in matches:
        seen.setdefault(sn, h)
    uniq = list(seen.items())
    if len(uniq) == 1:
        sn, h = uniq[0]
        print(f'[маршрут] Похоже на «{sn}» — {h}. Если фраза правда про это — подключи скилл сразу, без загрузки персон. Совпадение случайное (по смыслу фраза про другое) — действуй по смыслу: маршрут намёк, не приказ.')
    elif len(uniq) >= 2:
        names = ', '.join(sn for sn, _ in uniq)
        print(f'[маршрут] Задача матчит несколько маршрутов: {names}. Уточни у пользователя, что именно нужно, — не угадывай молча (арбитраж).')

# --- ПРОХОД 3: проект по keywords (latent: молчит пока в карте <2 проектов с keywords) ---
try:
    rows = [r for r in open('projects/map.md', encoding='utf-8').read().splitlines()
            if r.startswith('- **') and 'keywords:' in r]
    if len(rows) >= 2:
        matches = []
        for r in rows:
            nm = re.match(r'- \*\*([^*]+)\*\*', r)
            kw_part = r.split('keywords:', 1)[1]
            kws = [k.strip().lower() for k in re.split(r'[,;]', kw_part) if len(k.strip()) >= 3]
            if nm and any(hit_kw(k, lc) for k in kws):
                matches.append(nm.group(1).strip())
        matches = sorted(set(matches))
        if len(matches) == 1:
            print(f'[проект] Задача похожа на проект «{matches[0]}» — прочитай его дом (путь в projects/map.md) ПЕРЕД работой.')
        elif len(matches) >= 2:
            print(f'[проект] Задача матчит несколько проектов: {", ".join(matches)}. Спроси пользователя, про какой — не угадывай.')
except OSError:
    pass
PYEOF
fi

exit 0
