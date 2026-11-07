from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/office'))
from helpers import OfficeTest, ROOT

class Instructions(OfficeTest):
    def test_seven_sections_and_budget(self):
        text=(self.root/'AGENTS.md').read_text()
        self.assertEqual(text.count('\n## '), 7)
        self.assertLessEqual(len(text.encode()) + len((self.root/'CLAUDE.md').read_bytes()), 12*1024)
        self.assertTrue((self.root/'CLAUDE.md').read_text().startswith('@AGENTS.md'))
        for domain in ('me','work','projects','clients','knowledge','inbox','results'):
            self.assertEqual((self.root/domain/'CLAUDE.md').read_text(), '@AGENTS.md\n')
            self.assertTrue((self.root/domain/'AGENTS.md').is_file())

    def test_three_personal_blocks_fit_and_change_actions(self):
        from personalize import save_profile
        for owner in json.loads((ROOT/'tests/fixtures/owners.json').read_text()):
            fields=[]
            for key,kind,value in [('name','fact',owner['name']),('context','fact',owner['context']),('style','preference',owner['preference'])]:
                fields.append(dict(id=key,subject='owner',kind=kind,status='confirmed',value=value,source='synthetic confirmed interview',confirmed_at='2026-11-07'))
            data={'version':1,'facts':fields,'rules':[dict(basis='style',action=owner['action'],scope=owner['scope'],exception=owner['exception'])], 'boundaries':[]}
            if owner['boundary']: data['boundaries']=[dict(topic='Доход',status='declined')]
            save_profile(self.root,data)
            text=(self.root/'AGENTS.md').read_text()
            self.assertIn(owner['action'],text)
            self.assertLessEqual(len(text.encode()) + len((self.root/'CLAUDE.md').read_bytes()),12*1024)
