#!/bin/bash
# stage-check.sh — твёрдая самопроверка контракта этапа стройки (зовут этапы office-build
# ПЕРЕД пометкой «(готов)»; тесты гоняют в test/test-stage-check.sh; session-load зовёт
# режим audit как бэкстоп «этап закрыт, а артефактов нет»).
#
# Использование:
#   bash .claude/hooks/stage-check.sh <N>    — проверить этап N (1..8) перед закрытием
#   bash .claude/hooks/stage-check.sh audit  — проверить ВСЕ этапы, помеченные (готов) в журнале
#
# Вывод: stage<N>=ok | stage<N>=fail + строки «- что не так» (audit: audit=ok|audit=fail).
# Exit 0/1. Read-only: офис НЕ меняет, идемпотентен. Чистый bash + grep -F (байт-безопасен
# для кириллицы в любой локали); файлы в контекст не грузятся.

OFFICE_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$OFFICE_ROOT" || exit 1

BUILDLOG="team/ops/build-log.md"
FAILS=""
add_fail() { FAILS="${FAILS}- $1
"; }

# файл существует и непуст
need_file() { # <path> <что это>
  [ -s "$1" ] || add_fail "нет или пуст: $2 ($1)"
}
# файл содержит фиксированную строку-маркер (секцию формы / строку самопополнения)
need_marker() { # <path> <fixed-string> <что это>
  grep -qF -- "$2" "$1" 2>/dev/null || add_fail "$3: в $1 нет «$2»"
}
# целевой файл собран по форме шаблона: КАЖДАЯ секция «## …» шаблона есть в файле дословно.
# Секции читаются ИЗ шаблона — единственная точка правды формы; переименовал секцию в
# шаблоне → проверка сама начала требовать новую (руками список маркеров не дублируем).
need_form() { # <target> <template> <что это>
  local h
  [ -f "$2" ] || { add_fail "нет шаблона формы $2 — офис повреждён, обнови офис"; return; }
  # вербатим-копия шаблона (вместе с инструкцией-шапкой) — не заполненный файл, а обход формы
  if grep -qF 'шаблон — не заполнять здесь' "$1" 2>/dev/null; then
    add_fail "$3: $1 — копия шаблона с инструкцией-шапкой, а не заполненный под человека файл"
    return
  fi
  while IFS= read -r h; do
    grep -qF -- "$h" "$1" 2>/dev/null || add_fail "$3: в $1 нет секции «$h» (форма — $2)"
  done < <(grep '^## ' "$2")
}
# санитизация имени (slug) для сообщений: без переводов строк (иначе имя-ловушка подделает
# отдельную строку в блоке [дострой] session-load), с капом длины
safe_name() { printf '%s' "$1" | tr -d '\r\n' | cut -c1-80; }
# строка агента в team/map.md существует и заглушка снята
need_unstubbed() { # <core-path-substring> <имя>
  local line
  line=$(grep -F -- "$1" team/map.md 2>/dev/null | tail -1)
  if [ -z "$line" ]; then
    add_fail "в team/map.md нет строки агента $2 ($1)"
  elif printf '%s' "$line" | grep -qF 'заглушка'; then
    add_fail "в team/map.md у агента $2 не снята пометка [заглушка]"
  fi
}
# журнал содержит строку этапа N (в любом статусе).
# Формат строки статуса («^Этап N: … (открыт|готов)», последняя решает) продублирован в
# session-load.sh (петля возврата + bash-фолбэк) — менять ТОЛЬКО синхронно.
need_log_stage() { # <N>
  # [^0-9] после номера: «Этап 1:» и «Этап 1 —» считаем, «Этап 12» за «Этап 1» — нет.
  # Терпимость к пунктуации зеркалит парсер session-load (startswith('Этап')).
  grep -E "^[#[:space:]]*Этап $1[^0-9]" "$BUILDLOG" >/dev/null 2>&1 \
    || add_fail "в журнале $BUILDLOG нет строки «Этап $1: …»"
}
# готовые вещи в results/ (без служебных и форм). Конвенция офиса: служебная форма =
# basename с префиксом «_» и словом template (та же в update-office-sync и pre-push-pd-gate).
# Файл владельца вида kp-template.md (без «_») — НЕ форма, считается готовой вещью.
results_count() {
  find results -type f ! -name 'CLAUDE.md' ! -name 'INDEX.md' ! -path '*/_template/*' ! -name '_*template*' ! -name '.*' 2>/dev/null | wc -l | tr -d ' '
}

check_stage() {
  local trail f proj_found pdir cdir slug sec_n
  case "$1" in
    1)
      need_file "$BUILDLOG" "журнал стройки"
      need_log_stage 1
      need_file knowledge/summary.md "выжимка"
      need_form knowledge/summary.md knowledge/_summary-template.md "форма выжимки"
      need_marker knowledge/INDEX.md 'summary.md' "самопополнение: строка о выжимке в knowledge/INDEX.md"
      ;;
    2)
      need_log_stage 2
      need_file me/profile.md "профиль владельца"
      grep -qE 'Ядро собрано:\*{0,2}[[:space:]]*да' me/profile.md 2>/dev/null \
        || add_fail "в me/profile.md нет маркера «**Ядро собрано:** да» (его читает session-load)"
      need_form me/profile.md me/_profile-template.md "форма профиля"
      if grep -qF 'Владелец пока не представлен' CLAUDE.md 2>/dev/null; then
        add_fail "в корневом CLAUDE.md блок «Кто владелец офиса» всё ещё заглушка — впиши краткое ядро"
      fi
      [ "$(results_count)" -ge 1 ] || add_fail "в results/ нет первого подарка (ни одной готовой вещи)"
      ;;
    3)
      need_log_stage 3
      need_file team/agents/atlas/card.md "карточка коуча"
      need_marker team/agents/atlas/card.md '**Вектор:**' "слот сути карточки (_card-template.md)"
      need_marker team/agents/atlas/card.md '**Помогаю с:**' "слот сути карточки"
      need_marker team/agents/atlas/card.md '**Каким ты меня видишь:**' "слот сути карточки"
      trail=$(grep -F 'выбран пресет' team/agents/atlas/card.md 2>/dev/null | tail -1)
      if [ -z "$trail" ]; then
        add_fail "в карточке коуча нет строки-трейла «выбран пресет …» (маркер завершённости рождения)"
      elif printf '%s' "$trail" | grep -qF '<'; then
        add_fail "трейл карточки коуча содержит плейсхолдер <…> — карточка недостроена"
      fi
      for f in commitments observations log; do
        need_file "team/agents/atlas/memory/$f.md" "память коуча ($f)"
      done
      need_unstubbed 'team/agents/atlas/core.md' "Атлас"
      ;;
    4)
      need_log_stage 4
      need_file work/map.md "карта дела"
      # две легитимные ветки формы (work/_map-template.md): дело ИЛИ карта ситуации.
      # need_form тут не годится (шаблон несёт секции ОБЕИХ веток) — проверяем заголовок ветки,
      # копию шаблона и минимум секций.
      if grep -qF 'шаблон — не заполнять здесь' work/map.md 2>/dev/null; then
        add_fail "work/map.md — копия шаблона с инструкцией-шапкой, а не заполненная карта"
      fi
      if ! grep -qF '# Карта дела' work/map.md 2>/dev/null \
         && ! grep -qF '# Карта ситуации' work/map.md 2>/dev/null; then
        add_fail "в work/map.md нет заголовка «# Карта дела» / «# Карта ситуации» (форма — work/_map-template.md)"
      fi
      sec_n=$(grep -c '^## ' work/map.md 2>/dev/null)
      [ "${sec_n:-0}" -ge 2 ] \
        || add_fail "в work/map.md меньше двух секций «## …» — карта не собрана по форме"
      ;;
    5)
      need_log_stage 5
      [ "$(results_count)" -ge 2 ] \
        || add_fail "в results/ меньше двух готовых вещей — первое боевое дело не положено (подарок этапа 2 + вещь этапа 5)"
      ;;
    6)
      need_log_stage 6
      need_file team/agents/director/card.md "карточка Директора"
      need_marker team/agents/director/card.md '## Я —' "шапка карточки (_card-template.md)"
      need_file team/agents/director/memory.md "память Директора"
      grep -qE '20[0-9]{2}-[01][0-9]-[0-3][0-9]' team/agents/director/memory.md 2>/dev/null \
        || add_fail "в памяти Директора нет ни одной записи с датой ISO (форма — team/agents/_memory-template.md)"
      [ -f team/ops/today.md ] || add_fail "нет team/ops/today.md — первый день не заведён (форма — team/ops/_today-template.md)"
      need_unstubbed 'team/agents/director/core.md' "Директор"
      ;;
    7)
      need_log_stage 7
      # первый проект обязателен (ветка самоопределения тоже заводит проект)
      proj_found=0
      for pdir in projects/*/; do
        [ -d "$pdir" ] || continue
        slug=$(basename "$pdir")
        case "$slug" in _*) continue ;; esac   # _archive/ и прочие служебные — не проекты
        slug=$(safe_name "$slug")
        proj_found=1
        need_file "${pdir}map.md" "дом проекта $slug"
        need_form "${pdir}map.md" projects/_project-template.md "форма дома проекта $slug"
        # slug якорим хвостом «→ slug/map.md» и «slug/»: подстрока чужого slug (kurs в
        # zapusk-kursa) не должна давать ложный зачёт строки самопополнения
        need_marker projects/map.md "→ $slug/map.md" "самопополнение: строка проекта $slug (с хвостом → $slug/map.md) в карте projects/map.md"
        need_marker projects/INDEX.md "$slug/" "самопополнение: строка проекта $slug в projects/INDEX.md"
      done
      [ "$proj_found" = 1 ] || add_fail "нет ни одного проекта projects/<slug>/ — первый проект не заведён"
      # клиентов может не быть (этап не блокируется); есть карточка → форма + строка в INDEX
      for cdir in clients/*/; do
        [ -d "$cdir" ] || continue
        slug=$(basename "$cdir")
        case "$slug" in _*) continue ;; esac
        # папка seed-анкеты владельца (survey.json без карточки, SEED-CONTRACT) — не клиент
        [ -f "${cdir}survey.json" ] && [ ! -f "${cdir}README.md" ] && continue
        slug=$(safe_name "$slug")
        need_file "${cdir}README.md" "карточка клиента $slug"
        need_form "${cdir}README.md" clients/_client-template.md "форма карточки клиента $slug"
        need_marker clients/INDEX.md "$slug/" "самопополнение: строка клиента $slug в clients/INDEX.md"
      done
      ;;
    8)
      need_log_stage 8
      need_file MAP.md "карта офиса"
      if grep -qF 'Никита наполнит её на финале' MAP.md 2>/dev/null; then
        add_fail "MAP.md всё ещё заглушка — экскурсия не проведена, карта не наполнена"
      fi
      grep -qF '](' MAP.md 2>/dev/null \
        || add_fail "в MAP.md нет ни одной ссылки — карта «где что лежит» не наполнена"
      need_unstubbed 'team/agents/rita/core.md' "Рита"
      # память Риты пре-создана в болванке — ловим удаление/старый клон (симметрия с Директором)
      need_file team/agents/rita/memory.md "память Риты (форма — team/agents/_memory-template.md)"
      ;;
    *)
      echo "usage: stage-check.sh 1..8 | audit" >&2
      exit 1
      ;;
  esac
}

MODE="${1:-}"
case "$MODE" in
  1|2|3|4|5|6|7|8)
    check_stage "$MODE"
    if [ -z "$FAILS" ]; then
      echo "stage$MODE=ok"
    else
      echo "stage$MODE=fail"
      printf '%s' "$FAILS"
      exit 1
    fi
    ;;
  audit)
    # Журнала нет — проверять нечего (стройка не начата).
    [ -f "$BUILDLOG" ] || { echo "audit=ok"; exit 0; }
    # Скоуп audit — ЖИЗНЬ СТРОЙКИ. После «СТРОЙКА ЗАВЕРШЕНА» артефакты живут своей жизнью
    # (владелец правит, Рита архивирует) — гонять по ним контракт этапов вечно = ложные
    # [дострой] и тихая самодеятельность модели в данных владельца. Пост-финально проверяем
    # ТОЛЬКО полноту: финал объявлен → все 8 этапов обязаны быть (готов), иначе финал — призрак.
    finished=0
    grep -q 'СТРОЙКА ЗАВЕРШЕНА' "$BUILDLOG" 2>/dev/null && finished=1
    bad_stages=""; detail=""
    for n in 1 2 3 4 5 6 7 8; do
      # статус этапа = ПОСЛЕДНЯЯ строка «Этап N …» (журнал может вестись append-only);
      # [^0-9] — та же терпимость к пунктуации, что в need_log_stage
      last=$(grep -E "^[#[:space:]]*Этап $n[^0-9]" "$BUILDLOG" 2>/dev/null | tail -1)
      if ! printf '%s' "$last" | grep -qF '(готов)'; then
        if [ "$finished" = 1 ]; then
          bad_stages="$bad_stages stage$n"
          detail="${detail}stage$n=fail
- в журнале стоит «СТРОЙКА ЗАВЕРШЕНА», а этап $n не помечен (готов) — финал объявлен раньше стройки
"
        fi
        continue
      fi
      [ "$finished" = 1 ] && continue   # пост-финал: артефакты закрытых этапов не перепроверяем
      FAILS=""
      check_stage "$n"
      if [ -n "$FAILS" ]; then
        bad_stages="$bad_stages stage$n"
        detail="${detail}stage$n=fail
$FAILS"
      fi
    done
    if [ -z "$bad_stages" ]; then
      echo "audit=ok"
    else
      echo "audit=fail:$bad_stages"
      printf '%s' "$detail"
      exit 1
    fi
    ;;
  *)
    echo "usage: stage-check.sh 1..8 | audit" >&2
    exit 1
    ;;
esac
