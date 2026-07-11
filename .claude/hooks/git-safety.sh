#!/bin/bash
# Git Safety — автоматический локальный snapshot перед задачей (SessionStart).
# v3: + гейт «файл >50 МБ — стоп» — большой медиа-блоб не должен утонуть в истории git
# (её потом не вычистить). Медиа живёт в knowledge/raw/media/ вне git (.gitignore),
# но если что-то крупное просочилось в индекс — гейт ловит ДО коммита-снапшота.

MODE="${1:-snapshot}"  # snapshot | finish
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
MARKER_FILE="/tmp/.office-git-safety-$(echo "$PROJECT_DIR" | md5 -q 2>/dev/null || echo "$PROJECT_DIR" | md5sum | cut -d' ' -f1)"
MAX_BYTES=$((50 * 1024 * 1024))  # 50 МБ

cd "$PROJECT_DIR" || exit 0
git rev-parse --is-inside-work-tree &>/dev/null || exit 0

# --- гейт больших файлов: любой файл в рабочем дереве, не игнорируемый git, >50 МБ ---
big_files=""
# -z + quotePath=false: без этого git отдаёт кириллические имена в октальном экранировании
# («\320\262…»), [ -f ] по такой строке = false, и гейт молча пропускает файл. У русскоязычной
# аудитории почти ВСЕ медиа-имена кириллические — гейт был бы декоративным.
while IFS= read -r -d '' f; do
  [ -f "$f" ] || continue
  sz=$(wc -c < "$f" 2>/dev/null | tr -d ' ')
  if [ "${sz:-0}" -gt "$MAX_BYTES" ]; then
    big_files="$big_files\n     • $f ($((sz / 1024 / 1024)) МБ)"
  fi
done < <(git -c core.quotePath=false ls-files -z --others --cached --exclude-standard 2>/dev/null)

if [ -n "$big_files" ]; then
  # В stdout, а не stderr: SessionStart инжектит в контекст модели только stdout —
  # предупреждение в stderr модель не увидит и владельцу не передаст.
  echo "⚠️  Git Safety: файл(ы) больше 50 МБ — в git такое не кладём (историю потом не вычистить):"
  echo -e "$big_files"
  echo "   Крупное медиа держи в knowledge/raw/media/ (эта папка вне git). Снапшот пропущен."
  exit 0   # не коммитим этот заход, но и не роняем сессию
fi

if [ "$MODE" = "snapshot" ]; then
  BEFORE_SHA=$(git rev-parse --short HEAD 2>/dev/null)
  echo "$BEFORE_SHA" > "$MARKER_FILE"
  if ! git diff-index --quiet HEAD -- 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    git add -A 2>/dev/null
    # Честность по exit-code: коммит не прошёл (чаще всего не настроены user.name/user.email) —
    # НЕ говорим «сохранено». Ложное «snapshot created» = человек думает, что застрахован, а это не так.
    if git commit -m "🔒 snapshot before AI task: $(date +%Y-%m-%d\ %H:%M:%S)" --no-verify >/dev/null 2>&1; then
      echo "Git Safety: snapshot created (was $BEFORE_SHA, now $(git rev-parse --short HEAD 2>/dev/null))"
    else
      # stdout: иначе модель не узнает о провале и не предупредит владельца (весь смысл фикса).
      echo "⚠️  Git Safety: снапшот НЕ создан — git commit не прошёл (обычно не настроено имя: git config user.name / user.email). Этот заход работает без страховочной копии — скажи об этом владельцу."
    fi
  else
    echo "Git Safety: clean state, no snapshot needed ($BEFORE_SHA)"
  fi

elif [ "$MODE" = "finish" ]; then
  AFTER_SHA=$(git rev-parse --short HEAD 2>/dev/null)
  BEFORE_SHA=""
  [ -f "$MARKER_FILE" ] && BEFORE_SHA=$(cat "$MARKER_FILE")
  if [ -n "$BEFORE_SHA" ] && [ "$BEFORE_SHA" != "$AFTER_SHA" ]; then
    echo "Git Safety: Before=$BEFORE_SHA After=$AFTER_SHA"
  fi
  rm -f "$MARKER_FILE"
fi

exit 0
