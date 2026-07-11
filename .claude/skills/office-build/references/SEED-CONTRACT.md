# SEED-CONTRACT — формат `survey.json` (общий для двух сессий)

> Источник правды формата seed. Обе сессии (анкета `course-survey` и болванка офиса) держат ЭТОТ контракт.
> Меняешь схему — синхронно в обеих. Сессия болванки тестирует чтение против фикстуры ниже, не дожидаясь
> реальной анкеты. Путь файла в офисе ученика: **`clients/<me-slug>/survey.json`** (под ПД-гейтом).

## Схема

```json
{
  "meta": {
    "slug": "string — slug ученика (папка clients/<slug>/)",
    "filled_at": "ISO-дата заполнения анкеты"
  },
  "profile": {
    "name": "string — как зовут",
    "delo": "string — чем занимается / профессия",
    "nisha": "string|null — ниша/специализация",
    "uroven_ai": "novichok | uverennyy | razrabotchik"
  },
  "atlas_seed": {
    "atlas_preset": "myagkiy | pryamoy | analitik | situativnyy",
    "atlas_focus": "sales_avoid | last_mile | shiny_new | perfectionism | avoid_scary | none",
    "explain_level": "terminal_pugaet | norm | razrabotchik",
    "atlas_vector": "string|null — куда идёт (опц., свободный текст; может быть пустым/мусорным)"
  }
}
```

## Значения кнопок (enum) — что стоит за каждым

**`atlas_preset`** (характер коуча, вбирает и тон; = 4 пресета из `atlas/core.md`):
- `myagkiy` — мягкий поддерживающий (тепло, ирония тихая, давления ноль)
- `pryamoy` — прямой требовательный (в лоб, ирония острее, спрос жёстче)
- `analitik` — спокойный аналитик (ровный, по фактам, эмоций меньше)
- `situativnyy` — ситуативный (читает состояние, подстраивается) — ДЕФОЛТ

**`atlas_focus`** (главный паттерн ухода — куда сбегает от важного; кнопка «что про тебя вернее»):
- `sales_avoid` — откладываю продажи/деньги на потом, подменяю другим
- `last_mile` — бросаю на 80%, последний километр пресен
- `shiny_new` — распыляюсь на новые идеи вместо начатого
- `perfectionism` — залипаю в мелочах, полирую вместо выпуска
- `avoid_scary` — прокрастинирую страшное, ухожу в безопасное мелкое
- `none` — не выбрал / не про меня

**`explain_level`** (как объяснять — калибровка тона офиса):
- `terminal_pugaet` — терминал вижу впервые, объясняй бережно на примерах
- `norm` — норм пользуюсь ИИ, без разжёвывания
- `razrabotchik` — я технарь, коротко и по делу

## Фикстура (для тестов сессии болванки — задача 9)

`test/fixtures/survey-valid.json`:
```json
{
  "meta": { "slug": "maria-psy", "filled_at": "2026-07-11" },
  "profile": { "name": "Мария", "delo": "психолог", "nisha": "тревожность у подростков", "uroven_ai": "novichok" },
  "atlas_seed": { "atlas_preset": "myagkiy", "atlas_focus": "sales_avoid", "explain_level": "terminal_pugaet", "atlas_vector": "хочу выйти на 300к и перестать бояться поднять цену" }
}
```

Обязательные тест-кейсы чтения (задача 9): **valid** (выше) · **пустой atlas_vector** (`null`/`""`) ·
**битый JSON** · **отсутствует файл** · **atlas_focus=`none`** · **мусор в atlas_vector** (эмодзи/др. язык).
На всех, кроме valid — офис не падает, не цитирует мусор дословно, тихий фолбэк на живой диалог.
