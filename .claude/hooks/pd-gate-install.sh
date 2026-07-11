#!/usr/bin/env bash
# pd-gate-install.sh — автоустановка ПД-гейта (pre-push) на каждом старте сессии.
#
# Зачем: .git/hooks вне версионирования — клон шаблона приезжает БЕЗ pre-push.
# Хук ставит эталон .claude/hooks/pre-push-pd-gate.sh туда, куда РЕАЛЬНО смотрит git,
# и чинит сам себя: ученик снёс хук / приехала новая версия эталона → на следующем
# старте гейт снова на месте.
#
# Путь хуков берём ТОЛЬКО через `git rev-parse --git-path hooks` — он один правильно
# резолвит core.hooksPath (в т.ч. «~/…» и абсолютный), git worktree и случай «офис лежит
# подпапкой чужого репозитория». Ручная склейка ".git/hooks" тут врёт: создаёт фейковую
# папку внутри офиса и рапортует ok, пока git исполняет хуки совсем из другого места.
#
# Состояние — СВОЙ файл team/ops/pd-gate-state (одна строка, атомарная запись). Отдельный
# файл сознательно: SessionStart-хуки могут идти параллельно, а общий session-state пишется
# целиком (read-modify-write) → строка одного хука затирала бы строку другого.
#
# Статусы (их читают session-load.sh и этап 7 стройки — меняешь тут, правь и там):
#   pd_gate=ok                       — гейт стоит там, куда смотрит git (защиту обещать можно)
#   pd_gate=skip:not-git             — офис не под git: push невозможен, защита неприменима
#   pd_gate=error:no-source          — нет эталона .claude/hooks/pre-push-pd-gate.sh
#   pd_gate=error:hooks-external     — git смотрит на папку хуков ВНЕ офиса (чужой менеджер
#                                      хуков): туда не пишем и защиту НЕ обещаем
#   pd_gate=error:install-failed     — не удалось поставить (нет прав и т.п.)
#
# Defensive-контракт (нетехнарь, любая ОС): ЛЮБАЯ ошибка → тихая строка статуса, exit 0,
# НИКОГДА не traceback в лицо.

{
  OFFICE_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
  cd "$OFFICE_ROOT" || exit 0

  STATE_DIR="team/ops"
  STATE="$STATE_DIR/pd-gate-state"
  SRC=".claude/hooks/pre-push-pd-gate.sh"
  # Сигнатура гейта — строка-контракт в шапке pre-push-pd-gate.sh («# SIGNATURE: …»).
  MARKER='ПД-гейт офиса v3'

  set_state() {   # весь файл = одна строка; атомарно (tmp + mv), чужих ключей не трогаем
    mkdir -p "$STATE_DIR" 2>/dev/null || return 1
    local tmp="$STATE.tmp.$$"
    printf 'pd_gate=%s\n' "$1" > "$tmp" 2>/dev/null && mv "$tmp" "$STATE" 2>/dev/null
  }

  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { set_state "skip:not-git"; exit 0; }
  [ -f "$SRC" ] || { set_state "error:no-source"; exit 0; }

  # Куда git РЕАЛЬНО пойдёт за хуками (резолвит hooksPath, тильду, worktree, вложенный репо).
  hookdir=$(git rev-parse --git-path hooks 2>/dev/null) || { set_state "error:install-failed"; exit 0; }
  [ -n "$hookdir" ] || { set_state "error:install-failed"; exit 0; }
  case "$hookdir" in
    /*) abs_hookdir="$hookdir" ;;
    *)  abs_hookdir="$OFFICE_ROOT/$hookdir" ;;
  esac

  # Папка хуков вне офиса и вне его репозитория (чужой менеджер хуков, husky, глобальный
  # hooksPath) — не наша территория. Не пишем туда и, главное, НЕ рапортуем ok: иначе офис
  # пообещает владельцу защиту, которой нет.
  repo_root=$(git rev-parse --show-toplevel 2>/dev/null)
  case "$abs_hookdir" in
    "$OFFICE_ROOT"/*|"$repo_root"/*) : ;;
    *) set_state "error:hooks-external"; exit 0 ;;
  esac

  dst="$abs_hookdir/pre-push"

  # Идемпотентность: содержимое уже совпадает с эталоном → ничего не делаем.
  if [ -x "$dst" ] && cmp -s "$SRC" "$dst" 2>/dev/null; then
    set_state "ok"; exit 0
  fi

  mkdir -p "$abs_hookdir" 2>/dev/null || { set_state "error:install-failed"; exit 0; }

  # Чужой pre-push (не наш гейт) замещаем — мнимая защита хуже тишины — но НЕ теряем:
  # копия рядом, чтобы технический владелец мог вернуть свои проверки.
  if [ -f "$dst" ] && ! grep -qF "$MARKER" "$dst" 2>/dev/null; then
    cp "$dst" "$dst.backup-$(date +%Y%m%d%H%M%S)" 2>/dev/null
  fi

  # Атомарная установка: пишем во временный файл, ставим +x, потом mv (rename атомарен).
  # Иначе push, попавший в окно между cp и chmod, увидит недописанный/неисполняемый хук.
  tmp_hook="$abs_hookdir/.pre-push.tmp.$$"
  if cp "$SRC" "$tmp_hook" 2>/dev/null && chmod +x "$tmp_hook" 2>/dev/null \
       && mv "$tmp_hook" "$dst" 2>/dev/null; then
    set_state "ok"
  else
    [ -f "$tmp_hook" ] && command rm -f "$tmp_hook" 2>/dev/null
    set_state "error:install-failed"
  fi
  exit 0
} 2>/dev/null
