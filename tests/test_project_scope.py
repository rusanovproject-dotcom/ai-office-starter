import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/office'))
from helpers import OfficeTest

class ProjectScope(OfficeTest):
    def project(self,slug,name):
        from projects import create_project
        return create_project(self.root, slug, name, 'Учебный результат', 'Локальная страница проверена', ['только этот проект'], ['локальное чтение и правки'])

    def test_create_rules_and_repeat_no_overwrite(self):
        self.project('alpha','Альфа')
        p=self.root/'projects/alpha'
        for f in ('AGENTS.md','CLAUDE.md','map.md'):
            self.assertTrue((p/f).is_file())
        self.assertEqual((p/'CLAUDE.md').read_text(),'@AGENTS.md\n')
        (p/'map.md').write_text('Пользовательская правка')
        self.project('alpha','Альфа')
        self.assertEqual((p/'map.md').read_text(),'Пользовательская правка')

    def test_target_before_reference_and_cwd(self):
        from router import route
        self.project('alpha','Альфа'); self.project('beta','Бета')
        self.assertEqual(route(self.root,'Для Альфа сделай как в Бета')['project']['slug'],'alpha')
        deep=self.root/'projects/beta/deep/more'; deep.mkdir(parents=True)
        self.assertEqual(route(self.root,'Продолжай',cwd=deep)['project']['slug'],'beta')

    def test_foreign_cwd_and_traversal_rejected(self):
        from projects import create_project
        from router import route
        with self.assertRaises(ValueError): create_project(self.root,'../bad','Bad','x','y',[],[])
        with self.assertRaises(ValueError): route(self.root,'Продолжай',cwd=self.root.parent)

    def test_quoted_reference_does_not_switch_project(self):
        from router import route
        self.project('alpha','Альфа'); self.project('beta','Бета')
        deep=self.root/'projects/beta/deep'; deep.mkdir()
        self.assertEqual(route(self.root,'В примере сказано «Для Альфа сделай страницу», продолжай текущую задачу',cwd=deep)['project']['slug'],'beta')
        self.assertEqual(route(self.root,'Для проекта «Альфа» сделай страницу')['project']['slug'],'alpha')

    def test_zip_launcher_preserves_deep_project_context(self):
        import os,subprocess,sys
        deep=self.root/'projects/study/deep';deep.mkdir(parents=True)
        binaries=self.root.parent/'fake-client';binaries.mkdir()
        fake=binaries/'codex'
        fake.write_text('#!/bin/sh\nprintf "LAUNCH_CONTEXT=%s\\n" "$OFFICE_TASK_CWD"\n')
        fake.chmod(0o700)
        result=subprocess.run([sys.executable,str(self.root/'office-start.py'),'codex'],cwd=deep,env={**os.environ,'PATH':str(binaries)+os.pathsep+os.environ['PATH']},text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('LAUNCH_CONTEXT='+str(deep.resolve()),result.stdout)
