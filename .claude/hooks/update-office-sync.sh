#!/usr/bin/env bash
# update-office-sync.sh — файловая механика скилла update-office (один исполняемый контракт:
# его зовёт SKILL и его же гоняют тесты). Диалог и решения — на скилле, механика — здесь.
#
# Команды (все пути — от корня офиса):
#   backup <dir>        — скопировать [U]-данные владельца в <dir>; owner-блок из CLAUDE.md
#                         дополнительно кладётся ОТДЕЛЬНЫМ файлом <dir>/owner-block.md
#   restore <dir>       — вернуть [U]-данные поверх офиса + вшить owner-блок в свежий CLAUDE.md.
#                         Маркер-секция потеряна → НЕ падаем и НЕ вставляем молча: печатаем
#                         owner=lost (скилл предлагает владельцу восстановить — self-serve)
#   owner-restore <dir> — вставить owner-блок из бэкапа в CLAUDE.md (после «да» владельца)
#   verify <dir>        — сверка: каждый файл бэкапа существует в офисе и непуст; иначе exit 1
#
# [U]-данные владельца (что бэкапим) — зеркало списка в SKILL.md update-office.

set -uo pipefail
CMD="${1:-}"; DIR="${2:-}"
OFFICE_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$OFFICE_ROOT" || exit 1
[ -n "$CMD" ] && [ -n "$DIR" ] || { echo "usage: update-office-sync.sh backup|restore|owner-restore|verify|cleanup <dir>" >&2; exit 1; }
DIR="${DIR%/}"              # trailing slash ломает strip префикса в verify → вакуумный ok
export COPYFILE_DISABLE=1   # macOS: без мусорных ._ файлов в tar

MARKER='## Кто владелец офиса'

u_paths() {  # существующие [U]-пути (файлы и папки)
  local p
  for p in me work clients projects results knowledge inbox MAP.md team/map.md team/ops \
           team/agents/*/card.md team/agents/*/memory.md team/agents/*/memory; do
    [ -e "$p" ] && printf '%s\n' "$p"
  done
}

owner_py() {  # owner_py extract|merge|force <backup-dir>
  python3 - "$1" "$2" <<'PYEOF'
import re, sys, os
mode, bdir = sys.argv[1], sys.argv[2]
marker = '## Кто владелец офиса'
rx = re.compile(r'(' + re.escape(marker) + r'[^\n]*\n)(.*?)(?=\n## |\Z)', re.S)
blk_path = os.path.join(bdir, 'owner-block.md')

def read_claude():
    # Владелец мог пересохранить CLAUDE.md в Notepad → cp1251. Без фолбэка extract падал
    # UnicodeDecodeError, owner-блок не бэкапился, а backup всё равно рапортовал ok →
    # блок владельца терялся при обновлении НАВСЕГДА.
    for enc in ('utf-8', 'cp1251'):
        try: return open('CLAUDE.md', encoding=enc).read()
        except UnicodeDecodeError: continue
        except OSError: return None
    return None

if mode == 'extract':
    t = read_claude()
    if t is None: sys.exit(0)
    m = rx.search(t)
    if m and m.group(2).strip():
        open(blk_path, 'w', encoding='utf-8').write(m.group(2).strip() + '\n')
    sys.exit(0)

try: block = open(blk_path, encoding='utf-8').read().strip()
except OSError: print('owner=none'); sys.exit(0)
if not block: print('owner=none'); sys.exit(0)
t = read_claude()
if t is None: print('owner=lost'); sys.exit(0)

m = rx.search(t)
if m:
    t = t[:m.start(2)] + '\n' + block + '\n' + t[m.end(2):]
    open('CLAUDE.md', 'w', encoding='utf-8').write(t)
    print('owner=ok')
elif mode == 'force':
    lines = t.splitlines(True)
    idx = 1 if lines and lines[0].startswith('# ') else 0
    lines.insert(idx, '\n' + marker + '\n\n' + block + '\n')
    open('CLAUDE.md', 'w', encoding='utf-8').write(''.join(lines))
    print('owner=restored')
else:
    print('owner=lost')
PYEOF
}

case "$CMD" in
  backup)
    # Права 700 сразу при создании: в бэкапе — ПД клиентов владельца. Папка, читаемая другими
    # пользователями/процессами машины, — утечка вне модели угроз git/gitignore/pre-push.
    mkdir -p "$DIR" || exit 1
    chmod 700 "$DIR" 2>/dev/null
    # Непустой каталог → отказ: иначе stale-файлы прошлого бэкапа вернутся в офис при restore.
    if [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
      echo "backup=error: каталог $DIR не пуст — возьми новый (иначе вернём старые данные)" >&2; exit 1
    fi
    paths=(); while IFS= read -r p; do paths+=("$p"); done < <(u_paths)
    if [ "${#paths[@]}" -gt 0 ]; then
      # Шаблоны формы — константа офиса, не данные владельца: в бэкап не едут, иначе restore
      # вернёт СТАРЫЙ шаблон поверх приехавшего с обновлением нового, и форма замрёт на версии
      # дня установки. Конвенция офиса (та же в pre-push-pd-gate has_user_content и в
      # stage-check results_count — менять синхронно): форма = БАЗОВОЕ имя с префиксом «_»
      # и суффиксом «-template.md», плюс две точные папки-формы. ВАЖНО: паттерны якорим по
      # basename — файл владельца kp-template.md или его папка email-templates/ формой НЕ
      # считаются и обязаны ехать в бэкап (тест: test-update-office-sync.sh).
      tar cf - --exclude '_*-template.md' --exclude '_template' --exclude '_memory-template' \
        "${paths[@]}" 2>/dev/null | (cd "$DIR" && tar xf -) || exit 1
    fi
    command -v python3 >/dev/null 2>&1 && owner_py extract "$DIR"
    n=$(find "$DIR" -type f | wc -l | tr -d ' ')
    echo "backup=ok files=$n dir=$DIR"
    ;;
  restore)
    [ -d "$DIR" ] || { echo "restore=error: нет бэкапа $DIR" >&2; exit 1; }
    (cd "$DIR" && tar cf - --exclude 'owner-block.md' .) | tar xf - || exit 1
    if command -v python3 >/dev/null 2>&1; then owner_py merge "$DIR"; else echo "owner=manual"; fi
    echo "restore=ok"
    ;;
  owner-restore)
    command -v python3 >/dev/null 2>&1 || { echo "owner=manual" >&2; exit 1; }
    owner_py force "$DIR"
    ;;
  verify)
    missing=""
    while IFS= read -r f; do
      rel="${f#"$DIR"/}"
      # Проверяем СУЩЕСТВОВАНИЕ, не непустоту: у владельца бывает легитимно пустой файл
      # (заготовка заметки), и требование -s давало бы вечный ложный «данные потеряны» → откат.
      [ -e "$rel" ] || missing="$missing $rel"
    done < <(find "$DIR" -type f ! -name 'owner-block.md')
    if [ -n "$missing" ]; then
      echo "verify=fail: пропало:$missing" >&2; exit 1
    fi
    echo "verify=ok"
    ;;
  cleanup)
    # ПД в бэкапе не живёт дольше обновления: после успешной сверки папка сносится.
    case "$DIR" in
      ""|/|"$HOME") echo "cleanup=error: опасный путь" >&2; exit 1 ;;
    esac
    command rm -rf -- "$DIR" 2>/dev/null
    [ -d "$DIR" ] && { echo "cleanup=error: не удалось удалить $DIR" >&2; exit 1; }
    echo "cleanup=ok"
    ;;
  *) echo "unknown command: $CMD" >&2; exit 1 ;;
esac
