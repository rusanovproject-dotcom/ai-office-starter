import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/office'))
from helpers import OfficeTest

class Registry(OfficeTest):
    def record(self, name='Тест', slug='test'):
        self.put(f'team/agents/{slug}/core.md', '# Роль\nРеальная методика\n')
        self.put(f'team/agents/{slug}/card.md', 'Сценарии и границы\n')
        self.put(f'team/agents/{slug}/memory.md', '# Память\n')
        return {'id':slug,'name':name,'aliases':[], 'role':'помощник по учебным задачам', 'scope':['учебные задачи'], 'forbidden':['внешняя отправка'], 'core':f'team/agents/{slug}/core.md','card':f'team/agents/{slug}/card.md','memory':[f'team/agents/{slug}/memory.md'],'status':'active'}

    def test_duplicate_alias_rejected(self):
        from registry import validate_registry
        a=self.record(); b=self.record('Другой','other'); b['aliases']=['Тест']
        with self.assertRaises(ValueError): validate_registry(self.root, {'version':1,'agents':[a,b]})

    def test_missing_core_rejected(self):
        from registry import validate_registry
        a=self.record(); (self.root/a['core']).unlink()
        with self.assertRaises(ValueError): validate_registry(self.root, {'version':1,'agents':[a]})

    def test_generate_map_and_repeat(self):
        from registry import save_registry, validate_registry
        data={'version':1,'agents':[self.record()]}
        save_registry(self.root,data)
        before=(self.root/'team/map.md').read_bytes()
        save_registry(self.root,data)
        self.assertEqual((self.root/'team/map.md').read_bytes(),before)
        self.assertIn('Тест',before.decode())
        validate_registry(self.root)

    def test_role_cannot_be_alias(self):
        from registry import validate_registry
        data={'version':1,'agents':[self.record()]}
        data['agents'][0]['aliases']=['эксперт']
        with self.assertRaises(ValueError): validate_registry(self.root,data)

    def test_draft_can_wait_for_card_but_not_core(self):
        from registry import validate_registry
        record=self.record(); record['status']='draft'
        (self.root/record['card']).unlink()
        validate_registry(self.root,{'version':1,'agents':[record]})
        (self.root/record['core']).unlink()
        with self.assertRaises(ValueError): validate_registry(self.root,{'version':1,'agents':[record]})
