import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/office'))
from helpers import OfficeTest

class Personalization(OfficeTest):
    def profile(self):
        return {'version': 1, 'facts': [
            {'id': 'name', 'subject': 'owner', 'kind': 'fact', 'status': 'confirmed', 'value': 'Тестовый владелец', 'source': 'conversation', 'confirmed_at': '2026-11-07'},
            {'id': 'style', 'subject': 'owner', 'kind': 'preference', 'status': 'confirmed', 'value': 'на вы, технически', 'source': 'conversation', 'confirmed_at': '2026-11-07'}],
            'rules': [{'basis': 'style', 'action': 'Обращайся на вы, начинай с результата', 'scope': 'Рабочие ответы', 'exception': 'Существенные риски объясняй достаточно подробно'}],
            'boundaries': [{'topic': 'Доход', 'status': 'declined'}]}

    def test_personalize_preserves_contract_and_rebuilds(self):
        from personalize import save_profile
        source = self.profile()
        before = (self.root / 'AGENTS.md').read_text().split('<!-- owner:end -->')[1]
        save_profile(self.root, source)
        after = (self.root / 'AGENTS.md').read_text()
        self.assertEqual(after.split('<!-- owner:end -->')[1], before)
        self.assertIn('Обращайся на вы', after)
        self.assertNotIn('Доход', (self.root / 'knowledge/summary.md').read_text())
        source['facts'][1]['value'] = 'Подробно, с примерами'
        source['rules'][0]['action'] = 'Объясняй с примерами'
        save_profile(self.root, source)
        self.assertNotIn('Обращайся на вы', (self.root / 'AGENTS.md').read_text())

    def test_other_subject_and_hypothesis_not_owner(self):
        from personalize import save_profile
        p = self.profile()
        p['facts'] += [{'id': 'foreign', 'subject': 'client', 'kind': 'fact', 'status': 'confirmed', 'value': 'У клиента миллиард выручки', 'source': 'sample', 'confirmed_at': '2026-11-07'}]
        with self.assertRaises(ValueError): save_profile(self.root, p)
        p = self.profile()
        p['facts'][0]['status'] = 'hypothesis'
        save_profile(self.root, p)
        self.assertNotIn('Тестовый владелец', (self.root / 'AGENTS.md').read_text())

    def test_rule_requires_confirmed_preference(self):
        from personalize import save_profile
        p = self.profile()
        p['facts'][1]['status'] = 'unknown'
        with self.assertRaises(ValueError): save_profile(self.root, p)

    def test_explicit_correction_beats_old_import(self):
        from personalize import save_records, load_records
        first = {'id':'price', 'subject':'business', 'kind':'fact', 'status':'confirmed', 'value':'90', 'source':'owner correction', 'confirmed_at':'2026-11-07'}
        save_records(self.root, 'work', [first])
        old = dict(first, value='60', source='old deck', confirmed_at='2026-10-01')
        save_records(self.root, 'work', [old], imported=True)
        self.assertEqual(load_records(self.root, 'work')[0]['value'], '90')

    def test_goal_available_without_coach(self):
        from personalize import save_records, load_records
        goal={'id':'study', 'subject':'owner', 'kind':'intention', 'status':'confirmed', 'value':'Закончить учебный проект', 'scope':'project:study', 'horizon':'2026-12', 'state':'active', 'source':'owner', 'confirmed_at':'2026-11-07'}
        save_records(self.root, 'goals', [goal])
        self.assertEqual(load_records(self.root, 'goals'), [goal])
    def test_invalid_schema_and_values_do_not_write(self):
        from personalize import save_profile
        before=(self.root/'AGENTS.md').read_bytes()
        p=self.profile();p['version']=99
        with self.assertRaises(ValueError):save_profile(self.root,p)
        p=self.profile();p['facts'][0]['value']={'not':'a fact'}
        with self.assertRaises(ValueError):save_profile(self.root,p)
        self.assertEqual((self.root/'AGENTS.md').read_bytes(),before)
    def test_owner_delimiters_in_data_do_not_corrupt_contract(self):
        from personalize import save_profile
        before=(self.root/'AGENTS.md').read_bytes()
        value=self.profile();value['facts'][0]['value']='Имя <!-- owner:end -->'
        with self.assertRaises(ValueError):save_profile(self.root,value)
        self.assertEqual((self.root/'AGENTS.md').read_bytes(),before)
        self.assertFalse((self.root/'me/profile.md').exists())
