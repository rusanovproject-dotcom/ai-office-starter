from helpers import OfficeTest

class Integrity(OfficeTest):
    def test_truncation_does_not_verify(self):
        self.put('me/profile.md', 'Синтетический владелец, подтверждено: любит короткие ответы\n')
        backup = self.root.parent / 'backup'
        self.assertEqual(self.hook('update-office-sync.sh', 'backup', backup).returncode, 0)
        self.put('me/profile.md', '')
        self.assertNotEqual(self.hook('update-office-sync.sh', 'verify', backup).returncode, 0)

    def test_substitution_does_not_verify(self):
        self.put('me/profile.md', 'Синтетический профиль A\n')
        backup = self.root.parent / 'backup'
        self.hook('update-office-sync.sh', 'backup', backup)
        self.put('me/profile.md', 'Синтетический профиль Б\n')
        self.assertNotEqual(self.hook('update-office-sync.sh', 'verify', backup).returncode, 0)

import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/office'))

class UpdateMechanism(OfficeTest):
    def candidate(self):
        from common import digest, write_json
        candidate=self.root.parent/'candidate'
        shutil.copytree(self.root,candidate)
        files={p.relative_to(candidate).as_posix():digest(p.read_bytes()) for p in candidate.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.office' not in p.relative_to(candidate).parts}
        write_json(candidate/'.office/template-manifest.json',{'version':1,'files':files})
        write_json(self.root/'.office/template-manifest.json',{'version':1,'files':files})
        return candidate,files

    def test_hashes_empty_and_corrupt_backup(self):
        from update import backup,verify,restore
        self.put('me/profile.md','synthetic profile')
        self.put('results/empty.txt','')
        folder=self.root.parent/'backup'
        backup(self.root,folder)
        verify(self.root,folder)
        self.put('me/profile.md','')
        with self.assertRaises(ValueError):verify(self.root,folder)
        restore(self.root,folder)
        self.assertEqual((self.root/'me/profile.md').read_text(),'synthetic profile')
        (folder/'files/me/profile.md').write_text('backup corrupted')
        with self.assertRaises(ValueError):restore(self.root,folder)

    def test_owner_block_is_compared_and_cleanup_requires_integrity(self):
        from update import backup,verify,cleanup
        folder=self.root.parent/'backup'
        backup(self.root,folder)
        text=(self.root/'AGENTS.md').read_text()
        self.put('AGENTS.md',text.replace('Владелец пока не представлен.','Подменён владелец.'))
        with self.assertRaises(ValueError):verify(self.root,folder)
        with self.assertRaises(ValueError):cleanup(self.root,folder)
        self.assertTrue(folder.exists())

    def test_update_preserves_custom_data_and_repeat(self):
        from common import digest,write_json
        from update import apply_update,verify
        candidate,files=self.candidate()
        self.put('me/profile.md','synthetic owner profile')
        self.put('.agents/skills/custom/SKILL.md','---\nname: custom\ndescription: local custom\n---\nCustom\n')
        self.put('team/agents/custom/knowledge/source.md','synthetic custom knowledge')
        (candidate/'README.md').write_text('new template readme\n')
        files['README.md']=digest((candidate/'README.md').read_bytes())
        write_json(candidate/'.office/template-manifest.json',{'version':1,'files':files})
        backup_dir=self.root.parent/'backup'
        apply_update(self.root,candidate,backup_dir)
        self.assertEqual((self.root/'README.md').read_text(),'new template readme\n')
        self.assertEqual((self.root/'me/profile.md').read_text(),'synthetic owner profile')
        self.assertEqual((self.root/'team/agents/custom/knowledge/source.md').read_text(),'synthetic custom knowledge')
        verify(self.root,backup_dir)
        apply_update(self.root,candidate,self.root.parent/'backup2')

    def test_user_edit_conflicts_and_failed_write_rolls_back(self):
        from common import digest,write_json
        from update import apply_update
        from unittest.mock import patch
        candidate,files=self.candidate()
        (candidate/'README.md').write_text('new template\n')
        files['README.md']=digest((candidate/'README.md').read_bytes())
        write_json(candidate/'.office/template-manifest.json',{'version':1,'files':files})
        self.put('README.md','user changed template\n')
        with self.assertRaises(ValueError):apply_update(self.root,candidate,self.root.parent/'conflict-backup')
        self.assertEqual((self.root/'README.md').read_text(),'user changed template\n')
        self.assertTrue((self.root.parent/'conflict-backup/manifest.json').exists())
        self.put('README.md','restore original')
        # New baseline records this source before a simulated filesystem failure.
        files_current=dict(files,README=0)
        files_current.pop('README',None)
        files_current['README.md']=digest((self.root/'README.md').read_bytes())
        write_json(self.root/'.office/template-manifest.json',{'version':1,'files':files_current})
        import update
        original=update.atomic_write
        triggered=[]
        def fail_once(path,data):
            if Path(path).resolve()==(self.root/'README.md').resolve() and not triggered:
                triggered.append(True)
                raise PermissionError('synthetic midway failure')
            return original(path,data)
        with patch('update.atomic_write',side_effect=fail_once):
            with self.assertRaises(OSError):apply_update(self.root,candidate,self.root.parent/'failed-backup')
        self.assertEqual((self.root/'README.md').read_text(),'restore original')
        self.assertTrue((self.root.parent/'failed-backup/manifest.json').exists())

    def test_symlink_and_unsafe_cleanup_refused(self):
        from update import backup,cleanup
        external=self.root.parent/'outside.txt';external.write_text('external')
        (self.root/'results/link').symlink_to(external)
        with self.assertRaises(ValueError):backup(self.root,self.root.parent/'backup')
        with self.assertRaises(ValueError):cleanup(self.root,self.root)

    def test_owner_registry_and_map_are_verified(self):
        from update import backup,verify
        folder=self.root.parent/'backup'
        backup(self.root,folder)
        registry=json.loads((self.root/'team/registry.json').read_text())
        registry['agents'][0]['name']='Подменённое имя'
        from registry import save_registry
        save_registry(self.root,registry)
        with self.assertRaises(ValueError):verify(self.root,folder)

    def test_nested_secrets_are_not_backed_up(self):
        from update import backup
        self.put('secrets/api.json','synthetic secret')
        self.put('projects/demo/credentials/token.txt','synthetic secret')
        folder=self.root.parent/'backup'
        backup(self.root,folder)
        self.assertFalse((folder/'files/secrets/api.json').exists())
        self.assertFalse((folder/'files/projects/demo/credentials/token.txt').exists())

    def test_generated_edit_conflict_keeps_both_sources(self):
        from update import apply_update
        candidate,_=self.candidate()
        before=(self.root/'.agents/skills/office-build/SKILL.md').read_bytes()
        self.put('.claude/skills/office-build/SKILL.md','synthetic generated edit')
        with self.assertRaises(ValueError):apply_update(self.root,candidate,self.root.parent/'backup')
        self.assertEqual((self.root/'.agents/skills/office-build/SKILL.md').read_bytes(),before)
        self.assertEqual((self.root/'.claude/skills/office-build/SKILL.md').read_text(),'synthetic generated edit')

    def test_modified_wrapper_and_owner_envelope_do_not_silently_reset(self):
        from common import digest,write_json
        from update import apply_update,_merge_owner
        candidate,files=self.candidate()
        baseline={'version':1,'files':files,'agents_envelope':digest(_merge_owner((self.root/'AGENTS.md').read_text(),{'text':'<OWNER>'}).encode())}
        write_json(self.root/'.office/template-manifest.json',baseline)
        self.put('AGENTS.md',(self.root/'AGENTS.md').read_text()+'\nSynthetic owner instruction outside block\n')
        with self.assertRaises(ValueError):apply_update(self.root,candidate,self.root.parent/'backup')
        self.assertIn('Synthetic owner instruction outside block',(self.root/'AGENTS.md').read_text())

    def test_missing_file_and_corrupt_manifest_block_cleanup(self):
        from update import backup,verify,cleanup
        self.put('results/draft.txt','synthetic result')
        folder=self.root.parent/'backup'
        backup(self.root,folder)
        (self.root/'results/draft.txt').unlink()
        with self.assertRaises(ValueError):verify(self.root,folder)
        self.put('results/draft.txt','synthetic result')
        (folder/'manifest.json').write_text('{}')
        with self.assertRaises(ValueError):cleanup(self.root,folder)
        self.assertTrue(folder.exists())

    def test_failure_after_materialization_rolls_back_all_transaction_paths(self):
        from common import digest,write_json
        from update import apply_update,_files
        from unittest.mock import patch
        candidate,files=self.candidate()
        new=candidate/'.agents/skills/new-template-skill/SKILL.md'
        new.parent.mkdir(parents=True);new.write_text('---\nname: new-template-skill\ndescription: synthetic\n---\nNew\n')
        files[new.relative_to(candidate).as_posix()]=digest(new.read_bytes())
        write_json(candidate/'.office/template-manifest.json',{'version':1,'files':files})
        before={rel:p.read_bytes() for rel,p in _files(self.root).items()}
        with patch('update.materialize',side_effect=RuntimeError('synthetic post-write failure')):
            with self.assertRaises(RuntimeError):apply_update(self.root,candidate,self.root.parent/'backup')
        after={rel:p.read_bytes() for rel,p in _files(self.root).items()}
        self.assertEqual(before,after)

    def test_owner_registry_choices_survive_actual_update(self):
        from common import digest,write_json
        from update import apply_update,verify
        from registry import save_registry
        candidate,files=self.candidate()
        registry=json.loads((self.root/'team/registry.json').read_text())
        registry['agents'][0]['name']='Согласованное новое имя'
        save_registry(self.root,registry)
        (candidate/'README.md').write_text('new template release\n')
        files['README.md']=digest((candidate/'README.md').read_bytes())
        write_json(candidate/'.office/template-manifest.json',{'version':1,'files':files})
        folder=self.root.parent/'backup'
        apply_update(self.root,candidate,folder)
        actual=json.loads((self.root/'team/registry.json').read_text())
        self.assertEqual(actual['agents'][0],registry['agents'][0])
        verify(self.root,folder)

    def test_restore_recovers_registry_and_map(self):
        from update import backup,restore,verify
        from registry import load_registry,save_registry
        before=(self.root/'team/registry.json').read_bytes()
        original_map=(self.root/'team/map.md').read_bytes()
        folder=self.root.parent/'registry-restore'
        backup(self.root,folder)
        changed=load_registry(self.root);changed['agents'][0]['name']='Подмена'
        save_registry(self.root,changed)
        restore(self.root,folder)
        self.assertEqual((self.root/'team/registry.json').read_bytes(),before)
        self.assertEqual((self.root/'team/map.md').read_bytes(),original_map)
        verify(self.root,folder)
