#!/usr/bin/env bash
# SIGNATURE (СТРОКА-КОНТРАКТ, не менять — по ней pd-gate-install и session-load узнают свой гейт):
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

# Токены в ТЕЛЕ файлов (имя чистое — секрет внутри). Форматы под РЕАЛЬНУЮ ЦА офиса:
# Telegram-бот (`12345678:AA…`), Google/Gemini (`AIza…`), OpenAI/Anthropic/OpenRouter (`sk-…`),
# Stripe/Groq (`sk_`/`gsk_`), GitHub, AWS, Slack, JWT, пароль в connection-string, секрет в
# webhook-ссылке. Префиксные ключи якорим по границе слова: без якоря `sk[-_]` ловит невинные
# «risk-assessment», «desk-organization», «task_manager» и владелец получает ⛔ на чистой заметке.
# Голый hex (Deepgram/VK-ключ) — в отдельной переменной: он же формат Notion-id и git-SHA,
# поэтому его ищем ТОЛЬКО в тексте с вырезанными ссылками (см. ниже).
TOKEN_RE='(^|[^A-Za-z0-9_/-])(sk|gsk)[-_][A-Za-z0-9_-]{16,}|(^|[^A-Za-z0-9_-])(ghp|gho|ghs)_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_/+-]{15,}\.[A-Za-z0-9_/+-]{10,}|(^|[^0-9])[0-9]{8,10}:AA[A-Za-z0-9_-]{30,}|[a-zA-Z][a-zA-Z0-9+.-]*://[^[:space:]/@]+:[^[:space:]/@]{6,}@|hooks\.slack\.com/services/[A-Za-z0-9/]{20,}|api\.telegram\.org/bot[0-9]+:[A-Za-z0-9_-]+|[?&](api_?key|token|secret|access_token)=[A-Za-z0-9_.-]{16,}'

# Голый hex 32+ — форма, неразличимая между КЛЮЧОМ (Deepgram/VK), Notion-id и git-SHA.
# Различаем по КОНТЕКСТУ ПРИСВАИВАНИЯ: ключ человек вставляет как «ключ: <hex>», «key=<hex>»,
# «"token": "<hex>"». Упоминание коммита («откатились на 3f78…») присваиванием не является.
# Ссылки вырезаны заранее, поэтому Notion-id сюда не доходит. Компромисс сознательный: лучше
# пропустить хекс без контекста, чем блокировать обычную заметку и разувериться в гейте.
HEXKEY_RE='[:=][[:space:]"'\'']*[0-9a-f]{32,}'

# Текстовые файлы, тело которых сканируем: секрет уезжает и в .txt/.json/.yaml, не только в .md.
TEXT_GLOBS=('*.md' '*.txt' '*.json' '*.yaml' '*.yml' '*.csv' '*.env.example')

blocked=0

# --- накоплены ли РЕАЛЬНЫЕ данные владельца (не только clients/)? ---
# ПД живёт не только в карточках: результаты, проекты, сырьё, паспорт дела, нити, память.
# Content-скан ПД невозможен надёжно (любой .md может содержать имя клиента), поэтому
# гейт публичного remote срабатывает на ЛЮБОЙ накопленный пользовательский контент — так
# психолог/риэлтор физически не выложит наработанное в публику, даже ПД вне clients/.
has_user_content() {
  # Исключаем ТОЛЬКО структурные шаблонные файлы. ВАЖНО: карточка клиента = clients/<slug>/README.md,
  # поэтому README.md глобально исключать НЕЛЬЗЯ — режем лишь folder-level README (глубина 1) и
  # конкретный keeper knowledge/raw/README.md. CLAUDE.md/INDEX.md/дотфайлы — всегда служебные.
  # Формы шаблона — по конвенции офиса (та же в update-office-sync backup и stage-check,
  # менять синхронно): БАЗОВОЕ имя «_*-template.md» + точные папки _template/ и _memory-template/.
  # Якорим по basename нарочно: файл владельца kp-template.md или папка email-templates/ —
  # ДАННЫЕ владельца, гейт обязан их видеть.
  git ls-files 'clients/**' 'results/**' 'projects/**' 'knowledge/raw/**' \
               'me/**' 'work/**' 'team/ops/**' 2>/dev/null \
    | grep -vE '(^|/)(CLAUDE|INDEX)\.md$|(^|/)_[^/]*-template\.md$|/_template/|/_memory-template/|(^|/)\.[^/]+$|^knowledge/raw/README\.md$|^[a-z_]+/README\.md$' \
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

  # --- 1b) секреты в ТЕЛЕ пушимых текстовых файлов — имя чистое, токен внутри ---
  # Сканируем ДОБАВЛЕННЫЕ строки всей пушимой истории (git log -p), не только tip:
  # секрет, закоммиченный и потом «удалённый», всё равно уезжает с историей.
  # fail-safe тот же, что в (1): нечитаемый диапазон → сканируем всю локальную историю,
  # иначе на дыре в диапазоне (shallow / переписанный remote) скан молча пропускает всё.
  added="$(git log --format= -p "${range_args[@]}" -- "${TEXT_GLOBS[@]}" 2>/dev/null)"; gl=$?
  if [[ $gl -ne 0 ]]; then
    added="$(git log --format= -p "$local_sha" -- "${TEXT_GLOBS[@]}" 2>/dev/null)"
  fi
  added="$(printf '%s\n' "$added" | grep '^+' | grep -v '^+++')"

  # Префиксные токены и секреты-в-ссылках ищем в СЫРЫХ строках (пароль в connection-string и
  # webhook живут как раз внутри URL).
  token_hits="$(grep -E "$TOKEN_RE" <<<"$added")"

  # Голый hex-ключ и энтропию — в тексте БЕЗ ссылок и data:-URI: Notion-id, git-SHA, id в
  # Google-ссылке и инлайн-картинка base64 выглядят как секрет, но ими не являются. Ложный
  # блок на обычной заметке отпугнёт владельца от гейта сильнее, чем пропуск редкого формата.
  nourl="$(sed -E 's#data:[a-zA-Z0-9/+.-]+;base64,[A-Za-z0-9+/=]*##g; s#[a-zA-Z][a-zA-Z0-9+.-]*://[^[:space:])>"]*##g' <<<"$added")"
  hex_hits="$(grep -E "$HEXKEY_RE" <<<"$nourl")"
  # Энтропия: 40+ символов, все три класса. Пути («docs/plans/2026-07-…») исключены — символ
  # `/` не входит в класс, поэтому длинный путь распадается на короткие куски.
  entropy_hits="$(grep -oE '[A-Za-z0-9+=_]{40,}' <<<"$nourl" | grep '[A-Z]' | grep '[a-z]' | grep '[0-9]')"

  if [[ -n "$token_hits" || -n "$hex_hits" || -n "$entropy_hits" ]]; then
    blocked=1
    echo "⛔ ПД-ГЕЙТ: в теле пушимых файлов ('$local_ref') — похоже на токен/ключ/секрет. Ключам в git не место (любой remote):" >&2
    # показываем контекст, но сам секрет глушим — сообщение блока не должно его разгласить
    printf '%s\n' "$token_hits" "$hex_hits" "$entropy_hits" | grep -v '^$' | head -3 \
      | sed -E 's/[A-Za-z0-9+/=_.-]{12,}/[REDACTED]/g' | sed 's/^/     • /' >&2
    echo "     Убери секрет из файла (в .env — он в git не едет) и перепиши коммит, тогда push пройдёт." >&2
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
    echo "   Как починить: поставь GitHub CLI и войди (brew install gh && gh auth login) — гейт сам подтвердит" >&2
    echo "   приватность. Либо владелец сам убеждается, что репо приватный, и решает про push своими руками." >&2
  fi
fi

[[ "$blocked" == 1 ]] && {
  echo "   Решение об обходе гейта принимает ТОЛЬКО владелец офиса — руками, не через помощника." >&2
  echo "   Помощнику: обходить этот гейт запрещено. Скажи владельцу, что push остановлен и почему." >&2
}
exit "$blocked"
