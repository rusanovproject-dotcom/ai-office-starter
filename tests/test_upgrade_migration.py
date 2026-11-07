"""Synthetic copies of the original public template; no real offices are migrated."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/office'))
from helpers import OfficeTest,ROOT

class Migration(OfficeTest):
    def legacy(self):
        # Read the exact original source objects, not an invented approximation.
        legacy=self.root.parent/'legacy office'
        legacy.mkdir()
        listing=subprocess.run(['git','ls-tree','-r','--name-only','735c3e6'],cwd=ROOT,text=True,capture_output=True,check=True)
        for rel in listing.stdout.splitlines():
            data=subprocess.run(['git','show','735c3e6:'+rel],cwd=ROOT,capture_output=True,check=True).stdout
            path=legacy/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        return legacy
    def candidate(self):
        from common import digest,write_json
        candidate=self.root.parent/'candidate'
        shutil.copytree(self.root,candidate)
        files={p.relative_to(candidate).as_posix():digest(p.read_bytes()) for p in candidate.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.office' not in p.relative_to(candidate).parts}
        # The audited legacy baseline is part of the incoming ownership definition.
        rel='.office/legacy-manifest.json';files[rel]=digest((candidate/rel).read_bytes())
        write_json(candidate/'.office/template-manifest.json',{'version':1,'files':files})
        return candidate
    def test_legacy_profile_goal_and_custom_skill_survive(self):
        from update import apply_update,verify
        legacy=self.legacy();candidate=self.candidate()
        before=(legacy/'CLAUDE.md').read_text()
        before=before.replace('Владелец пока не представлен. Если это первый запуск — см. рефлекс «первый заход» ниже.','Синтетический владелец: Марина. Предпочитает на вы, коротко.')
        (legacy/'CLAUDE.md').write_text(before)
        profile=legacy/'me/profile.md';profile.write_bytes('Старый синтетический профиль\n'.encode())
        log=legacy/'team/ops/build-log.md';log.write_text('Этап 2: человек (готов)\nЭтап 3: коуч (открыт)\n')
        card=legacy/'team/agents/atlas/card.md';card.write_text('# Коуч\n**Вектор:** Хочу закончить учебный проект своими руками\n')
        custom=legacy/'.claude/skills/custom/SKILL.md';custom.parent.mkdir(parents=True);custom.write_text('---\nname: custom\ndescription: Synthetic local procedure\n---\nCustom\n')
        original_profile=profile.read_bytes();original_log=log.read_bytes();original_card=card.read_bytes();original_custom=custom.read_bytes()
        folder=self.root.parent/'migration backup'
        result=apply_update(legacy,candidate,folder)
        self.assertTrue(result['legacy'])
        self.assertEqual(profile.read_bytes(),original_profile)
        self.assertEqual(log.read_bytes(),original_log)
        self.assertIn(original_card,card.read_bytes())
        self.assertIn('Хочу закончить учебный проект своими руками',(legacy/'me/goals.md').read_text())
        self.assertIn('needs-confirmation',(legacy/'me/goals.md').read_text())
        self.assertEqual(custom.read_bytes(),original_custom)
        self.assertEqual((legacy/'.agents/skills/custom/SKILL.md').read_bytes(),original_custom)
        self.assertTrue((legacy/'CLAUDE.md').read_text().startswith('@AGENTS.md'))
        self.assertIn('Синтетический владелец: Марина.',(legacy/'AGENTS.md').read_text())
        verify(legacy,folder)
    def test_legacy_changed_builtin_skill_conflict_preserves_both(self):
        from update import apply_update
        legacy=self.legacy();candidate=self.candidate()
        skill=legacy/'.claude/skills/office-build/SKILL.md'
        skill.write_text('synthetic owner edit in stock skill')
        old=skill.read_bytes()
        with self.assertRaises(ValueError):apply_update(legacy,candidate,self.root.parent/'conflict-backup')
        self.assertEqual(skill.read_bytes(),old)
        self.assertTrue((self.root.parent/'conflict-backup/files/.claude/skills/office-build/SKILL.md').exists())
    def test_custom_legacy_agent_is_not_silently_dropped(self):
        from update import apply_update
        from registry import load_registry
        legacy=self.legacy();candidate=self.candidate()
        folder=legacy/'team/agents/custom';folder.mkdir()
        (folder/'core.md').write_text('# София\nЛокальный помощник, без отправки.\n')
        (folder/'card.md').write_text('# София\nТолько черновики.\n')
        (folder/'memory.md').write_text('# Память\nСинтетическая запись.\n')
        with (legacy/'team/map.md').open('a') as f:f.write('\n- **София** (Соня) — помощник по черновикам → team/agents/custom/core.md\n')
        apply_update(legacy,candidate,self.root.parent/'custom-agent-backup')
        item=next((a for a in load_registry(legacy)['agents'] if a['id']=='custom'),None)
        self.assertIsNotNone(item)
        self.assertEqual(item['name'],'София')
        self.assertIn('Соня',item['aliases'])
        self.assertEqual(item['status'],'draft')
        self.assertIn('София',(legacy/'team/map.md').read_text())
    def custom_legacy(self, aliases='Соня', core='core.md', directory_memory=False):
        legacy=self.legacy()
        folder=legacy/'team/agents/custom';folder.mkdir()
        (folder/core).write_text('# София\nЛокальные черновики.\n')
        (folder/'card.md').write_text('# София\nКарточка черновика.\n')
        if directory_memory:
            (folder/'memory').mkdir();(folder/'memory/log.md').write_text('# Журнал\nСинтетическая память.\n')
        else:(folder/'memory.md').write_text('# Память\nСинтетическая память.\n')
        with (legacy/'team/map.md').open('a') as f:f.write(f'\n- **София** ({aliases}) — помощник → team/agents/custom/{core}\n')
        return legacy

    def test_compound_role_alias_is_blocked(self):
        from update import apply_update
        legacy=self.custom_legacy('Налоговый консультант')
        with self.assertRaises(ValueError):apply_update(legacy,self.candidate(),self.root.parent/'role-backup')
        self.assertIn('Налоговый консультант',(legacy/'team/map.md').read_text())

    def test_legacy_claude_core_and_directory_memory_kept(self):
        from update import apply_update
        from registry import load_registry
        legacy=self.custom_legacy(core='CLAUDE.md',directory_memory=True)
        apply_update(legacy,self.candidate(),self.root.parent/'claude-agent-backup')
        item=next(a for a in load_registry(legacy)['agents'] if a['id']=='custom')
        self.assertEqual(item['core'],'team/agents/custom/CLAUDE.md')
        self.assertEqual(item['memory'],['team/agents/custom/memory/log.md'])

    def test_conflicting_legacy_rows_are_not_silently_dropped(self):
        from update import apply_update
        legacy=self.custom_legacy()
        with (legacy/'team/map.md').open('a') as f:f.write('- **Лидия** (Лида) → team/agents/custom/core.md\n')
        original=(legacy/'team/map.md').read_bytes()
        with self.assertRaises(ValueError):apply_update(legacy,self.candidate(),self.root.parent/'double-backup')
        self.assertEqual((legacy/'team/map.md').read_bytes(),original)
