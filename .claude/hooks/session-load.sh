#!/bin/bash
# session-load.sh — ЕДИНСТВЕННЫЙ SessionStart-инжект офиса v3 (второй не заводить:
# хук-налог компаундится за ход). Чистый bash: файлы >лимита в контекст НЕ грузятся.
#
# Инжектит по приоритету:
#   1. Петля недели 2 (SPEC §7) — ОДНА строка незакрытого: недостроенный этап (build-log)
#      ИЛИ открытая нить (threads.md). Два режима возврата, тон без вины.
#   2. Профиль владельца (me/profile.md) — если онбординг ядра пройден.
#   3. Память Директора (хвост) — если Директор развёрнут.
#   4. До 2 сигналов: новый офис / inbox / лимиты памяти.
# Состояние каденсов: team/ops/session-state (gitignored). Каденсы в СЕССИЯХ, не днях.

OFFICE_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$OFFICE_ROOT" || exit 0

STATE_DIR="team/ops"
STATE="$STATE_DIR/session-state"
mkdir -p "$STATE_DIR" 2>/dev/null

get_state() { grep -m1 "^$1=" "$STATE" 2>/dev/null | cut -d= -f2-; }
set_state() {
  local k="$1" v="$2" tmp="$STATE.tmp.$$"   # уникальный tmp: параллельные сессии не затирают друг друга
  { grep -v "^$k=" "$STATE" 2>/dev/null; echo "$k=$v"; } > "$tmp" && mv "$tmp" "$STATE"
}

# Счётчик сессий. Санитайзер обязателен: state мог приехать с CRLF (Windows-редактор) или
# просто битым — «3\r + 1» роняет арифметику bash в stderr КАЖДЫЙ старт, значение застревает
# навсегда (самолечения нет), ротация формулировок замирает на первой, каденсы ломаются.
counter=$(get_state counter | tr -cd '0-9')
counter=$(( ${counter:-0} + 1 ))
set_state counter "$counter"

echo "=== [офис: контекст сессии] ==="

BUILDLOG="team/ops/build-log.md"
THREADS="team/ops/threads.md"
PROFILE="me/profile.md"

# ── 1. ПЕТЛЯ НЕДЕЛИ 2 — одна строка незакрытого (высший приоритет) ───────────
# Источник A: недостроенный этап стройки. В build-log ищем последнюю строку
# «Этап N: … (открыт)» — маркер незакрытого этапа. Закрытые помечены «(готов)».
# Источник B: открытая нить (threads.md) — «в прошлый раз начали Y».
# today.md ИСТОЧНИКОМ БЫТЬ НЕ МОЖЕТ (затирается днём) — сюда не смотрим.
# Извлечение — через python3: bash в локали C.UTF-8 рвёт кириллицу при param-expansion/read
# внутри скрипта (проверено: значение корраптится до одного байта). python3 обрабатывает UTF-8
# корректно и печатает готовую строку [возврат]. Нет python3 → bash-фолбэк с ОБЩИМ сообщением
# без интерполяции имени (имя — не критично, критичен сам факт возврата и режим).
loop_printed=0
if command -v python3 >/dev/null 2>&1; then
  loop_out=$(BUILDLOG="$BUILDLOG" THREADS="$THREADS" COUNTER="$counter" python3 - <<'PYEOF'
import os
bl, th = os.environ.get('BUILDLOG',''), os.environ.get('THREADS','')
try: counter = int(os.environ.get('COUNTER', '0'))
except ValueError: counter = 0

def read(p):
    # Нетехнарь мог пересохранить журнал в Notepad → cp1251. Пробуем utf-8, затем cp1251;
    # любая другая беда — молча пусто (петля возврата деградирует, но traceback в лицо не летит).
    for enc in ('utf-8', 'cp1251'):
        try: return open(p, encoding=enc).read().splitlines()
        except UnicodeDecodeError: continue
        except (OSError, ValueError): return []
    return []

# Источник A — открытый этап стройки. Журнал может вестись append-only (закрытие дописывает
# новую строку «(готов)», не редактируя старую «(открыт)»). Поэтому берём ПОСЛЕДНЮЮ строку
# со статусом и считаем открытым только если её статус — «(открыт)».
open_stage = None
for ln in read(bl):
    # Маркером статуса считаем ТОЛЬКО строку этапа («Этап N: …»), иначе свободный текст
    # журнала («результат: пост (готов)») ложно гасит незакрытость и убивает петлю возврата.
    # Терпим решётки/отступ перед «Этап» (модель иногда пишет заголовком — S2).
    s = ln.lstrip('# ').strip()
    if not s.startswith('Этап'):
        continue
    if '(открыт)' in s:
        open_stage = s.split('(открыт)')[0].strip()
    elif '(готов)' in s:
        open_stage = None   # более поздний «(готов)» гасит незакрытость
# Пасхалка возврата: не сухая инструкция, а ГОТОВАЯ тёплая строка про реальный хвост.
# Ротация формулировок по номеру сессии — чтобы офис не бубнил одно и то же каждый заход.
# Хвоста нет → блок молчит: фолбэк = обычное нейтральное приветствие модели.
STAGE_LINES = [
    'в прошлый раз мы остановились на «{x}» — помню. вернёмся или сегодня другое?',
    'у нас недостроено: «{x}». я на месте, подхватим?',
    'держу в голове «{x}». как будешь готов — продолжим ровно с того места',
    'с прошлого раза ждёт «{x}». занырнём или сначала что-то свежее?',
    'помню про «{x}». если сегодня не до этого — нормально, оно не убежит',
]
THREAD_LINES = [
    'в прошлый раз начали «{x}» — помню, вернёмся?',
    'у меня осталась зарубка: «{x}». продолжим или сегодня другое?',
    'держу нить: «{x}». подхватить?',
    'с прошлого раза висит «{x}» — я не забыл. как ты, готов вернуться?',
    'помню про «{x}». скажешь — продолжим, скажешь — отложим, обе кнопки работают',
]

if open_stage:
    line = STAGE_LINES[counter % len(STAGE_LINES)].format(x=open_stage)
    print(f'скажи это своими словами, тепло и без вины: «{line}» '
          f'(режим — СТРОЙКА: подхвати этап по журналу, не переспрашивай отвеченное)')
else:
    # Источник B — первая содержательная нить
    thread = None
    for ln in read(th):
        s = ln.strip()
        # пропускаем пустые, заголовки, комменты (в т.ч. хвост блок-коммента) и цитаты
        if (not s or s.startswith('#') or s.startswith('<!--') or s.startswith('-->')
                or s.endswith('-->') or s.startswith('>')):
            continue
        if s.startswith('- '): s = s[2:]
        elif s.startswith('* '): s = s[2:]
        if s:
            thread = s; break
    if thread:
        line = THREAD_LINES[counter % len(THREAD_LINES)].format(x=thread)
        print(f'скажи это своими словами, тепло и без вины: «{line}» '
              f'(режим — ДЕЛО: спроси, продолжаем это или у него другое на сегодня)')
PYEOF
)
  if [ -n "$loop_out" ]; then
    echo ""
    echo "[возврат] $loop_out"
    loop_printed=1
  fi
fi
if [ "$loop_printed" = 0 ]; then
  # bash-фолбэк без python3: определяем ТОЛЬКО факт незакрытого (grep -F байт-безопасен),
  # имя не интерполируем.
  # append-only-безопасно: последняя строка со статусом решает (grep -F байт-безопасен)
  last_status=""
  [ -f "$BUILDLOG" ] && last_status=$(grep -E '^[#[:space:]]*Этап' "$BUILDLOG" 2>/dev/null | grep -F -e '(открыт)' -e '(готов)' | tail -1)
  if printf '%s' "$last_status" | grep -qF '(открыт)'; then
    echo ""
    echo "[возврат] Стройка не закрыта (см. последний открытый этап в team/ops/build-log.md). Начни с «мы остановились тут — продолжим?» (без вины). Режим — СТРОЙКА: подхвати по журналу, не переспрашивай отвеченное."
  elif [ -f "$THREADS" ] && grep -qvE '^[[:space:]]*(#|<!--|-->|>|$)' "$THREADS" 2>/dev/null; then
    echo ""
    echo "[возврат] Есть открытая нить (team/ops/threads.md). Режим — ДЕЛО: спроси, продолжаем прошлое или другое на сегодня. Без вины."
  fi
fi

# ── 1b. Бэкстоп контракта стройки: этап помечен (готов), а артефактов нет ────
# stage-check.sh audit проверяет ВСЕ закрытые этапы (read-only, дёшево). Модель могла
# закрыть этап, забыв дособрать/проверить, — этот блок ловит дыру на следующем же заходе.
# Полный вывод не вываливаем (контекст-налог): шапка + первые строки причин.
if [ -f "$BUILDLOG" ] && [ -f .claude/hooks/stage-check.sh ]; then
  audit_out=$(bash .claude/hooks/stage-check.sh audit 2>/dev/null)
  # -n: хук, упавший БЕЗ вывода (битый файл после кривого обновления), не должен рождать
  # пустой [дострой] с приказом дособирать неизвестно что
  if [ $? -ne 0 ] && [ -n "$audit_out" ]; then
    echo ""
    echo "[дострой] Контракт стройки нарушен: $(printf '%s' "$audit_out" | head -1) — этап закрыт в журнале, но обязательные артефакты не на месте:"
    printf '%s\n' "$audit_out" | grep '^- ' | head -5
    echo "Дособери молча по контракту этапа (открой его файл в .claude/skills/office-build/references/, секция «Контракт этапа», прогони stage-check до ok). Без драматизации и извинений: доделай в фоне текущего разговора; уместно — упомяни владельцу одной спокойной строкой, что довёл мелочи стройки (без терминов и путей). Скрывать сделанное не нужно — не нужно только пугать кухней."
  fi
fi

# ── 2. Профиль владельца / сигнал нового офиса ──────────────────────────────
# Маркер онбординга ядра: «**Ядро собрано:** да» в profile.md (ставит этап 2).
onboarded=false
if [ -f "$PROFILE" ] && grep -qE 'Ядро собрано:\*{0,2}[[:space:]]*да' "$PROFILE" 2>/dev/null; then
  onboarded=true
  echo ""
  # Дамп профиля в каждую сессию снят (контекст-налог, а человеку — «плашка-анкета» в лицо).
  # Вместо него указатель: агент читает файл сам перед содержательной работой.
  echo "[профиль] ядро собрано. Перед содержательной работой прочитай me/profile.md (кто владелец, как с ним работать) — не переспрашивай то, что там уже есть."
fi

# ── 3. Хвост памяти Директора (если развёрнут — волна 1b) ────────────────────
DMEM="team/agents/director/memory.md"
if [ -f "$DMEM" ]; then
  echo ""
  echo "[память] хвост памяти Директора:"
  tail -15 "$DMEM"
fi

# ── 4. Сигналы (максимум 2) ─────────────────────────────────────────────────
sig_keys=(); sig_texts=(); sig_windows=()
# add_sig <key> <text> [cadence_window]
# cadence_window>0: после показа сигнал молчит столько СЕССИЙ (антидубль, IDEAS #11) —
#   чтобы офис не бубнил одно и то же каждый заход. Пусто/0 = показывать всегда
#   (критичные/самоочищающиеся: newoffice гаснет сам со стройкой, prepush — безопасность).
add_sig() { sig_keys+=("$1"); sig_texts+=("$2"); sig_windows+=("${3:-0}"); }

# Новый офис: нет журнала И нет профиля → стройка ещё не начата.
if [ ! -f "$BUILDLOG" ] && ! $onboarded; then
  add_sig newoffice "Офис новый — стройка не начата. Если пользователь пишет что угодно (даже «привет») → это первый запуск: подключается скилл office-build, Никита-эксперт представляется и ведёт этап 1. Не жди отдельной команды."
fi

# Бэкстоп защиты «по конструкции»: есть push-remote, но НАШ ПД-гейт не стоит ТАМ, КУДА СМОТРИТ git.
# Дефолт офиса — БЕЗ remote; добавил remote → гейт обязан стоять до первого push.
# Путь хуков берём через `git rev-parse --git-path hooks` (резолвит core.hooksPath, «~», worktree,
# офис-подпапку чужого репо) — ручная склейка ".git/hooks" врёт. Сверяем СИГНАТУРУ: гасим сигнал
# только если лежит именно наш гейт, а не любой pre-push (чужой шим = защита мнимая, хуже тишины).
if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && [ -n "$(git remote 2>/dev/null)" ]; then
  hookdir=$(git rev-parse --git-path hooks 2>/dev/null)
  gate_ok=0
  if [ -n "$hookdir" ] && [ -x "$hookdir/pre-push" ] \
       && grep -qF 'ПД-гейт офиса v3' "$hookdir/pre-push" 2>/dev/null; then
    gate_ok=1
  fi
  if [ "$gate_ok" = 0 ]; then
    add_sig prepush "⚠️ У офиса есть внешний адрес (remote), но ПД-гейт на отправку НЕ стоит там, куда смотрит git ($hookdir/pre-push). Клиентские данные могут уехать без проверки. Гейт ставится сам при старте офиса — перезапусти офис; если сигнал остался, скажи об этом владельцу и не делай push."
  fi
fi

# inbox с неразобранным (служебное не считаем).
inbox_n=$(find inbox -type f ! -name "README.md" ! -name "CLAUDE.md" ! -name "INDEX.md" ! -name ".gitkeep" ! -name ".*" 2>/dev/null | wc -l | tr -d ' ')
if [ "${inbox_n:-0}" -gt 0 ]; then
  add_sig inbox "В inbox/ лежит файлов: $inbox_n. Скажи пользователю: «есть неразобранное — скажи \"разбери inbox\", я всё разложу»." 4
fi

# Лимиты памяти агентов (200 строк soft). У коуча память — папка memory/*.md;
# архивы (archive.md, memory-archive.md) растут по конструкции — их не считаем.
over_limit=""
for m in team/agents/*/memory.md team/agents/*/memory/*.md; do
  [ -f "$m" ] || continue
  case "$(basename "$m")" in archive.md|memory-archive.md) continue ;; esac
  ml=$(wc -l < "$m" | tr -d ' ')
  agent_dir=$(dirname "$m"); [ "$(basename "$agent_dir")" = "memory" ] && agent_dir=$(dirname "$agent_dir")
  [ "$ml" -gt 200 ] && over_limit="$over_limit $(basename "$agent_dir")/$(basename "$m")($ml)"
done
if [ -n "$over_limit" ]; then
  add_sig memlimit "Память переросла лимит 200 строк:$over_limit. Попроси агента прибраться (дубли слить, устаревшее в memory-archive.md); текучку памяти ведёт Рита." 4
fi

# Показ сигналов. Критичные/самоочищающиеся (window=0: newoffice, prepush-безопасность) —
# БЕЗУСЛОВНО, вне лимита и антидубля: их нельзя проглотить порядком или каденсом.
# Cadence-сигналы (window>0: inbox, memlimit) — максимум 2 за сессию И антидубль: показанный
# недавно молчит window сессий (реестр sig_last_<key>, каденс по counter). Заголовок — только
# если реально что-то показали.
cad_shown=0; header=0
for i in "${!sig_keys[@]}"; do
  key="${sig_keys[$i]}"; win="${sig_windows[$i]:-0}"
  if [ "$win" -gt 0 ] 2>/dev/null; then
    [ "$cad_shown" -ge 2 ] && continue          # лимит 2 — только для cadence-сигналов
    last=$(get_state "sig_last_$key")
    # last>counter (битый/скопированный из другого офиса state) → НЕ подавляем: показываем
    # и перезапишем sig_last, иначе неаварийный сигнал залипнет в тишине на сотни сессий.
    if [ -n "$last" ] && [ "$last" -le "$counter" ] 2>/dev/null \
         && [ "$((counter - last))" -lt "$win" ]; then
      continue   # показан недавно → антидубль
    fi
  fi
  if [ "$header" = 0 ]; then echo ""; echo "[сигналы]"; header=1; fi
  echo "- ${sig_texts[$i]}"
  if [ "$win" -gt 0 ] 2>/dev/null; then
    set_state "sig_last_$key" "$counter"
    cad_shown=$((cad_shown + 1))
  fi
done

exit 0
