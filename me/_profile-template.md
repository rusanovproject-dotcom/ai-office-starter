# Форма профиля

Канон me/profile.md: заголовок, **Ядро собрано:** да, затем fenced `office-profile` JSON.
Обязательные ключи: version:1, facts:[], rules:[], boundaries:[].
Каждый факт: id, subject:owner, kind:fact|intention|preference|hypothesis, status:confirmed|hypothesis|unknown|undecided, value; для confirmed — source и confirmed_at (ISO дата).
Имена id name/context попадают в корень только если kind fact и status confirmed; context — 1 устойчивая фраза, без доходов, цен и дедлайнов.
Правило: basis (id подтверждённого preference), action, scope, exception. Покажи человеку преобразование до сохранения.
Граница: только topic и status:declined|undecided, если человек разрешил помнить саму тему. Не включай личный ответ.
Записывает personalize.py из stdin; не редактируй owner-блок AGENTS или summary вручную.
Для принятой цели используй me/goals.md; для дела — work/map.md.
