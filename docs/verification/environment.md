# Проверенная среда

2026-11-07, macOS Darwin arm64. Исходник: 735c3e62bdfbab884e9d6ca36c22cce69ea47a8d, локальная ветка codex/universal-client-office. До изменений были только два неотслеживаемых документа docs/plans/2026-11-07-universal-client-office*.md; они сохранены без правок. Remote не менялся, fetch/push/публикация не выполнялись.

- Python 3.14.6, стандартная библиотека, внешних pip-зависимостей нет.
- Codex CLI 0.166.0, авторизация доступна; hooks stable true. Фактические smoke-результаты записываются отдельно.
- Claude Code 2.1.319, loggedIn:false, authMethod:none. Модельные сценарии Claude и смена Codex ↔ Claude SKIPPED по последующему явному указанию пользователя «клод не трогаем. его не тестим сейчас». Новых запусков после этого указания нет; версия и прежний init-only не доказывают работу модели.
- Windows/Linux отсутствуют: проверки этих ОС SKIPPED. Поставка не объявлена проверенной на них.

Независимая проверка CLI выполнила Codex debug prompt-input в пустых HOME/CODEX_HOME: корневые AGENTS/skills обнаруживаются в Git-офисе, в ZIP из корня. Из глубокой подпапки без Git корневой контекст не обнаруживается. Поэтому для ZIP предусмотрен launcher с подъёмом к .office-template.json. Claude init-only в пустом HOME и CLAUDE_CONFIG_DIR выполнил синтетический SessionStart без авторизации; это только lifecycle.

Источники контрактов: [Codex hooks](https://learn.chatgpt.com/docs/hooks), [AGENTS discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [skills](https://learn.chatgpt.com/docs/build-skills), [Claude hooks](https://code.claude.com/docs/en/hooks), [Claude memory](https://code.claude.com/docs/en/memory). Это документация, не результаты runtime.
