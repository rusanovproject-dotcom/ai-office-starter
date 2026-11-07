# Фактическая локальная приёмка

Все данные синтетические. Codex CLI 0.166.0, macOS arm64; отдельные HOME/CODEX_HOME. Пользовательские AGENTS, навыки и память Никиты не копировались. Стандартные материалы самого установленного CLI могут присутствовать; реальные чтения и hashes записаны. Один запуск на условие, без статистического вывода.

| Сценарий | Доказательство | Статус |
|---|---|---|
| Приветствие и чистый старт | greeting: реальная модель, bootstrap, office-build, журнал | PASS Codex |
| Подтверждённый профиль и персональный корень | onboarding + foreign-facts: реальные записи и проверка канона | PASS Codex |
| Полезная вещь без обязательного интервью | onboarding/reply + two-projects HTML | PASS Codex |
| Три пары без/с профилем | Анна, Борис, Вера; полные выходы в evals | PASS Codex |
| Постоянная поправка и новый чат | Anna correction: другой процесс ответа; прежняя настройка не навязана | PASS Codex |
| Нерелевантная задача | 391, ноль commands, без явного чтения биографии | PASS по поведению; bootstrap этого раннего запуска SKIPPED |
| Постоянная смена цели и новый чат | goal-behavior + bootstrap-runtime: тот же id, новая область/горизонт, новый HOME помнит новую цель | PASS Codex |
| Директор + явный skill | goal-change: действующая synthetic роль + office-project-add создали проект с правилами | PASS Codex |
| Несколько результатов и разовая подробность | multi-output: 2 карточки, отдельный пост без ПД; профиль/owner-блок byte-identical | PASS Codex |
| Найм и персональная роль | hiring draft/две пробы, activation после подтверждения, вызов Соня | PASS Codex; роль в чате, не native subagent |
| Упоминание/цитата/роль не имя | исполняемые routing tests и пробы маршрута при hiring | PASS механики; отдельная модельная отрицательная проба не заявлена |
| Два проекта, референс и подпапка | two-projects из alpha/deep через launcher: HTML Альфы, сумма Беты не перенесена | PASS Codex |
| Страница доведена до результата | index.html; отрисовка проверена родительским in-app browser | PASS; Chrome внутри CLI-пробы был недоступен |
| Чужой субъект и намерение | foreign-facts: аналитик по найму, руководство intention, чужой пример не сохранён | PASS Codex |
| Отказ и запрет записи | onboarding/foreign-facts + новая сессия; marker не найден в файлах офиса | PASS Codex; история хоста вне управления |
| Поправка цены и сохранение цели | continuation после обновления: 90→120, старая презентация не откатила | PASS Codex |
| Нативные hooks и доверие | штатное /hooks, native arithmetic 0commands + создан state; alias-name из контекста 0commands | PASS Codex |
| Resume и compact | реальный exec resume; TUI compact 22с; следующий запрос361, native provenance свежего bootstrap | PASS Codex; контекст после compact приходит перед следующим model request |
| Обновление заполненной копии | actual-update:11 owner files byte-identical, затем continuation | PASS локально |
| Ошибки/откат/legacy migration | update, upgrade, privacy, state tests и independent findings | PASS механики |
| Claude model / смена клиентов | не запускать по указанию пользователя | SKIPPED, не PASS |
| Windows/Linux/Codex Desktop | отдельные среды отсутствуют | SKIPPED, не PASS |

Финальные ZIP extraction и local Git clone прошли bootstrap/validators и реальные model smoke из глубокой подпапки: docs/verification/package-candidate.json, clone-mechanical.json, zip-smoke.json, clone-smoke.json. Наличие файла не считается model/runtime-проверкой. Raw traces вне продукта: .office/verification/runtime; короткие выходы и native provenance — docs/verification/.
