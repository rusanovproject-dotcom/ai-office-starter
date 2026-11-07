import json
from helpers import OfficeTest

class Routing(OfficeTest):
    def test_role_not_alias(self):
        result = self.hook('prompt-inject.sh', stdin=json.dumps({'prompt': 'Эксперт по налогам нужен'}, ensure_ascii=False))
        self.assertNotIn('[агент] Это вызов агента «Никита»', result.stdout)

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/office'))

class NewRouting(OfficeTest):
    def test_name_alias_role_mention(self):
        from router import route
        from registry import load_registry, save_registry
        data=load_registry(self.root)
        data['agents'][0]['aliases']=['Ник']
        save_registry(self.root,data)
        self.assertEqual(route(self.root,'Ник, помоги')['agent']['id'],'nikita')
        self.assertIsNone(route(self.root,'Эксперт по налогам нужен')['agent'])
        self.assertIsNone(route(self.root,'В письме написано «Никита, помоги»')['agent'])

    def test_explicit_role_and_skill_preserved(self):
        from router import route
        result=route(self.root,'Директор, используй office-project-add для проекта')
        self.assertEqual(result['agent']['id'],'director')
        self.assertIn('office-project-add',result['skills'])

    def test_multiple_tasks_preserved(self):
        from router import route
        result=route(self.root,'Разбери клиентов и напиши пост')
        self.assertIn('office-project-add',result['skills'])
        self.assertIn('office-firstwin',result['skills'])
        self.assertFalse(result['needs_clarification'])

    def test_missing_core_is_not_routable(self):
        from router import route
        (self.root/'team/agents/nikita/core.md').unlink()
        with self.assertRaises(ValueError): route(self.root,'Никита, помоги')
