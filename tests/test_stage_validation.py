import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/office"))
from helpers import OfficeTest

class Readiness(OfficeTest):
    def test_empty_coach_not_ready(self):
        self.put('team/ops/build-log.md', 'Этап 3: коуч (открыт)\n')
        self.put('team/agents/atlas/card.md', '**Вектор:**\n**Помогаю с:**\n**Каким ты меня видишь:**\nвыбран пресет мягкий\n')
        for f in ('commitments', 'observations', 'log'):
            self.put(f'team/agents/atlas/memory/{f}.md', '# Память\n')
        self.put('team/map.md', '- **Атлас** — team/agents/atlas/core.md\n')
        (self.root / 'team/agents/atlas/core.md').unlink()
        self.assertNotEqual(self.hook('stage-check.sh', '3').returncode, 0)
    def test_filled_card_missing_core_and_placeholder_rejected(self):
        import sys
        from pathlib import Path
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/office'))
        from stage_check import check_stage
        self.put('team/ops/build-log.md','Этап 3: коуч (открыт)\n')
        self.put('team/agents/atlas/card.md','**За что отвечаю:** рефлексия\n**Вектор:** согласовать следующий шаг\n**Помогаю с:** разобрать выбор\n**Каким ты меня видишь:** уважительно, кратко\n')
        for f in ('commitments','observations','log'):
            self.put(f'team/agents/atlas/memory/{f}.md','# Память\nЗаписи пока не требуются.\n')
        from registry import load_registry, save_registry
        data=load_registry(self.root)
        next(a for a in data['agents'] if a['id']=='atlas')['status']='active'
        save_registry(self.root,data)
        self.assertTrue(check_stage(self.root,3).startswith('PASS'))
        self.put('team/agents/atlas/card.md','**За что отвечаю:** рефлексия\n**Вектор:** <цель>\n**Помогаю с:** разобрать выбор\n**Каким ты меня видишь:** кратко\n')
        with self.assertRaises(ValueError):check_stage(self.root,3)
        (self.root/'team/agents/atlas/core.md').unlink()
        with self.assertRaises(ValueError):check_stage(self.root,3)
    def test_skipped_coach_and_false_final(self):
        import sys
        from pathlib import Path
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/office'))
        from stage_check import check_stage,audit
        self.put('team/ops/build-log.md','Этап 3: коуч (пропущен)\n')
        self.assertTrue(check_stage(self.root,3).startswith('SKIPPED:'))
        self.put('team/ops/build-log.md','Этап 3: коуч (пропущен)\nСТРОЙКА ЗАВЕРШЕНА\n')
        self.assertTrue(audit(self.root))
    def test_stage6_validates_calendar_and_iana_zone_but_accepts_history(self):
        from stage_check import check_stage
        self.put('team/ops/build-log.md','Этап 6: директор (открыт)\n')
        self.put('team/agents/director/card.md','**За что отвечаю:** организация работы\n**Вектор:** завершить задачу\n**Помогаю с:** выбрать следующий шаг\n**Каким ты меня видишь:** кратко и конкретно\n')
        self.put('team/agents/director/memory.md','# Память\nНет записей.\n')
        from registry import load_registry, save_registry
        data=load_registry(self.root)
        next(a for a in data['agents'] if a['id']=='director')['status']='active'
        save_registry(self.root,data)
        for day,zone in (('2026-99-99','Asia/Ho_Chi_Minh'),('2026-11-07','Mars/Olympus')):
            with self.subTest(day=day,zone=zone):
                self.put('team/ops/today.md',f'Дата: {day}\nTimezone: {zone}\nMIT: завершить синтетическую задачу\n')
                with self.assertRaises(ValueError):check_stage(self.root,6)
        self.put('team/ops/today.md','Дата: 2020-02-29\nTimezone: Asia/Ho_Chi_Minh\nMIT: историческая запись\n')
        self.assertEqual(check_stage(self.root,6),'PASS:structure-only')

    def test_complete_draft_roles_cannot_finish_stages(self):
        from stage_check import check_stage
        from registry import load_registry
        from hire import activate_employee
        self.put('team/ops/build-log.md', 'Этап 3: коуч (готов)\nЭтап 6: директор (готов)\nЭтап 8: память (готов)\n')
        self.put('team/ops/today.md', 'Дата: 2026-11-07\nTimezone: Asia/Ho_Chi_Minh\nMIT: завершить синтетическую задачу\n')
        self.put('MAP.md', '# Карта\n[Команда](team/map.md)\n')
        data=load_registry(self.root)
        for stage,slug in ((3,'atlas'),(6,'director'),(8,'rita')):
            item=next(a for a in data['agents'] if a['id']==slug)
            self.put(item['card'], '**За что отвечаю:** согласованная роль\n**Вектор:** завершить задачу\n**Помогаю с:** следующий шаг\n**Каким ты меня видишь:** уважительно\n')
            for path in item['memory']:
                self.put(path, '# Память\nРазрешённых записей пока нет.\n')
            with self.subTest(stage=stage,status='draft'):
                with self.assertRaisesRegex(ValueError,'не активирован'):
                    check_stage(self.root,stage)
            self.put(f'results/{slug}-trial.md', '# Синтетическая проба\nВыбран один следующий шаг, исходные данные сохранены.\n')
            activate_employee(self.root,slug,{
                'task':'Согласовать следующий шаг на синтетической задаче',
                'output':'Один шаг выбран, исходные данные сохранены',
                'artifact':f'results/{slug}-trial.md',
                'criterion':'Один следующий шаг без потери данных',
                'assessment':'Критерий выполнен: шаг выделен, исходные данные сохранены',
                'confirmed':True,
            })
            with self.subTest(stage=stage,status='active'):
                self.assertEqual(check_stage(self.root,stage),'PASS:structure-only')
