#!/usr/bin/env bash
# pre-push — ПД-гейт офиса v3.
#
# Философия v3 «по конструкции»: офис по дефолту БЕЗ push-remote (живёт локально,
# снапшоты локальные, обновления тянутся из upstream pull-only). clients/ здесь
# ВЕРСИОНИРУЕТСЯ — это актив владельца, он должен лежать в git. Опасность одна:
# уехать в ПУБЛИЧНЫЙ remote. Этот гейт — вторая линия (defense in depth):
#   1) секреты / транскрипты / медиа — блок ВСЕГДА (в любой remote);
#   2) реальные карточки clients/ + remote выглядит публичным ИЛИ видимость
#      не удалось подтвердить → блок (fail-safe: неизвестное = рискованное).
#
# Установка (копия, НЕ симлинк — .git/hooks вне версионирования):
#   cp .claude/hooks/pre-push-pd-gate.sh .git/hooks/pre-push && chmod +x .git/hooks/pre-push
# Это делает скилл-стройка при первой настройке push (по явной просьбе владельца).
# Осознанный обход гейта существует, но это решение ВЛАДЕЛЬЦА и делается его руками.
# Помощнику (модели) обходить гейт запрещено — не подсказывай и не исполняй обход.

set -uo pipefail

REMOTE_NAME="${1:-}"
REMOTE_URL="${2:-}"

# Секреты / приватные ключи / медиа / документы — не allowlist по «медиа», а широкий охват:
# голосовые Telegram (.ogg/.opus), сканы/фото клиента (.jpg/.png/.pdf/.heic), ssh-ключи,
# .netrc/.pgpass/.envrc, service-account — всё это ПД/секреты, которым не место в git.
FORBIDDEN_RE='(^|/)\.env($|\.)|(^|/)\.envrc$|\.pem$|\.key$|(^|/)id_(rsa|dsa|ecdsa|ed25519)|(^|/)\.netrc$|(^|/)\.pgpass$|(^|/)credentials(\.|/|$)|(^|/)secrets(\.|/|$)|(^|/)config\.env$|(^|/)service-account|transcript|\.(mp4|mov|mkv|webm|mp3|m4a|wav|ogg|oga|opus|aac|flac)$|\.(pdf|jpe?g|png|heic)$'

blocked=0

# --- накоплены ли РЕАЛЬНЫЕ данные владельца (не только clients/)? ---
# ПД живёт не только в карточках: результаты, проекты, сырьё, паспорт дела, нити, память.
# Content-скан ПД невозможен надёжно (любой .md может содержать имя клиента), поэтому
# гейт публичного remote срабатывает на ЛЮБОЙ накопленный пользовательский контент — так
# психолог/риэлтор физически не выложит наработанное в публику, даже ПД вне clients/.
has_user_content() {
  # Исключаем ТОЛЬКО структурные шаблонные файлы. ВАЖНО: карточка клиента = clients/<slug>/README.md,
  # поэтому README.md глобально исключать НЕЛЬЗЯ — режем лишь folder-level README (глубина 1) и
  # конкретный keeper knowledge/raw/README.md. CLAUDE.md/INDEX.md/_template/дотфайлы — всегда служебные.
  git ls-files 'clients/**' 'results/**' 'projects/**' 'knowledge/raw/**' \
               'me/**' 'work/**' 'team/ops/**' 2>/dev/null \
    | grep -vE '(^|/)(CLAUDE|INDEX)\.md$|/_template/|(^|/)\.[^/]+$|^knowledge/raw/README\.md$|^[a-z_]+/README\.md$' \
    | grep -q .
}

# --- безопасен ли remote для ПД? безопасно=1 / риск=0 / неизвестно=2 (fail-safe = риск) ---
# ТОЛЬКО PRIVATE считаем безопасным. PUBLIC и INTERNAL (виден всей организации) — риск.
remote_is_public() {
  command -v gh >/dev/null 2>&1 || return 2
  local slug
  slug=$(printf '%s' "$REMOTE_URL" | sed -E 's#(git@[^:]+:|https?://[^/]+/)##; s#\.git/?$##')
  [[ "$slug" == */* ]] || return 2
  local vis
  vis=$(gh repo view "$slug" --json visibility -q .visibility 2>/dev/null) || return 2
  [[ "$vis" == "PRIVATE" ]] && return 1   # приватный — безопасно
  return 0                                 # PUBLIC / INTERNAL / иное — риск
}

# --- 1) секреты / медиа / транскрипты — блок в любой remote ------------------
while read -r local_ref local_sha remote_ref remote_sha; do
  [[ -z "${local_sha:-}" ]] && continue
  [[ "$local_sha" =~ ^0+$ ]] && continue
  if [[ "$remote_sha" =~ ^0+$ ]]; then
    range_args=("$local_sha" --not --remotes="$REMOTE_NAME")
  else
    range_args=("$remote_sha..$local_sha")
  fi
  # fail-safe: если диапазон нечитаем (переписанная история remote, shallow-клон) — git log
  # даёт ненулевой код; тогда НЕ пропускаем молча, а сканируем всю локальную историю ветки
  # (полный охват), чтобы секрет/ПД не проскочил на дыре в диапазоне.
  raw="$(git log --diff-filter=d --name-only --format= "${range_args[@]}" 2>/dev/null)"; gl=$?
  if [[ $gl -ne 0 ]]; then
    raw="$(git log --diff-filter=d --name-only --format= "$local_sha" 2>/dev/null)"
  fi
  files="$(printf '%s\n' "$raw" | sort -u)"
  if grep -qiE "$FORBIDDEN_RE" <<<"$files"; then
    blocked=1
    echo "⛔ ПД-ГЕЙТ: в коммитах '$local_ref' — секреты / транскрипты / медиа:" >&2
    grep -iE "$FORBIDDEN_RE" <<<"$files" | head -5 | sed 's/^/     • /' >&2
  fi
done

# --- 2) накопленные данные владельца + публичный/неизвестный remote → блок ----
if has_user_content; then
  remote_is_public; vis_code=$?
  if [[ "$vis_code" == 0 ]]; then
    blocked=1
    echo "⛔ ПД-ГЕЙТ: remote '$REMOTE_NAME' ПУБЛИЧНЫЙ/общий, а в офисе есть твои данные (клиенты, наработки, проекты)." >&2
    echo "   Это приватное. В публичный репо ему нельзя. Нужен приватный remote." >&2
  elif [[ "$vis_code" == 2 ]]; then
    blocked=1
    echo "⛔ ПД-ГЕЙТ: не удалось подтвердить, что remote '$REMOTE_NAME' приватный (нет gh CLI или репо недоступен)," >&2
    echo "   а в офисе есть твои данные (клиенты, наработки, проекты). Из осторожности push заблокирован." >&2
  fi
fi

[[ "$blocked" == 1 ]] && {
  echo "   Решение об обходе гейта принимает ТОЛЬКО владелец офиса — руками, не через помощника." >&2
  echo "   Помощнику: обходить этот гейт запрещено. Скажи владельцу, что push остановлен и почему." >&2
}
exit "$blocked"
