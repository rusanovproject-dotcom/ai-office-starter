import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/office'))
from helpers import OfficeTest

class Bootstrap(OfficeTest):
    def git(self,*args):
        return subprocess.run(['git',*args],cwd=self.root,text=True,capture_output=True,env={**os.environ,'GIT_CONFIG_GLOBAL':os.devnull,'GIT_CONFIG_NOSYSTEM':'1'})
    def test_zip_and_foreign_parent_repo(self):
        from bootstrap import install_gate
        self.assertEqual(install_gate(self.root),'SKIPPED:not-git')
        subprocess.run(['git','init','-q',str(self.root.parent)],check=True)
        self.assertEqual(install_gate(self.root),'BLOCKED:foreign-repository')
    def test_install_and_foreign_hooks_path(self):
        from bootstrap import install_gate
        self.git('init','-q')
        self.assertEqual(install_gate(self.root),'PASS')
        self.assertTrue((self.root/'.git/hooks/pre-push').is_file())
        external=self.root.parent/'external-hooks';external.mkdir()
        self.git('config','core.hooksPath',str(external))
        self.assertEqual(install_gate(self.root),'BLOCKED:hooks-external')
        self.assertEqual(list(external.iterdir()),[])
    def test_foreign_hook_not_replaced(self):
        from bootstrap import install_gate
        self.git('init','-q')
        hook=self.put('.git/hooks/pre-push','#!/bin/sh\necho foreign\n')
        self.assertEqual(install_gate(self.root),'BLOCKED:foreign-pre-push')
        self.assertIn('foreign',hook.read_text())
    def test_snapshot_does_not_commit_index_or_copy_secrets(self):
        from bootstrap import snapshot
        self.git('init','-q')
        self.put('.env','SYNTHETIC_SECRET=example')
        self.put('secrets/api.json','synthetic')
        self.put('results/work.txt','synthetic work')
        result=snapshot(self.root)
        self.assertTrue(result.startswith('PASS:'))
        self.assertEqual(self.git('diff','--cached','--name-only').stdout,'')
        for p in (self.root/'.office/snapshots').rglob('*'):
            self.assertNotEqual(p.name,'.env')
            self.assertNotIn('secrets',p.parts)
    def test_no_git_and_install_error(self):
        from unittest.mock import patch
        from bootstrap import install_gate
        with patch('bootstrap.shutil.which',return_value=None):
            self.assertEqual(install_gate(self.root),'BLOCKED:no-git')
        self.git('init','-q')
        with patch('bootstrap.atomic_write',side_effect=PermissionError('synthetic access denied')):
            self.assertEqual(install_gate(self.root),'BLOCKED:install-failed')
    def test_adapter_json_and_no_python_diagnostic(self):
        import json
        p=subprocess.run([sys.executable,str(self.root/'scripts/office/adapter.py'),'codex'],input=json.dumps({'hook_event_name':'UserPromptSubmit','cwd':str(self.root),'prompt':'Эксперт по налогам нужен'}),cwd=self.root,text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['hookSpecificOutput']['hookEventName'],'UserPromptSubmit')
        # PATH contains only dirname, deliberately no Python or Git.
        binaries=self.root.parent/'bin';binaries.mkdir()
        import shutil
        (binaries/'dirname').symlink_to(shutil.which('dirname'))
        p=subprocess.run(['/bin/bash',str(self.root/'scripts/office/run.sh'),'bootstrap'],env={**os.environ,'PATH':str(binaries)},text=True,capture_output=True)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('BLOCKED: Python',p.stderr)
    def test_snapshot_does_not_follow_runtime_symlink(self):
        from bootstrap import snapshot
        outside=self.root.parent/'outside';outside.mkdir()
        import shutil
        runtime=self.root/'.office'
        if runtime.exists():shutil.rmtree(runtime)
        runtime.symlink_to(outside,target_is_directory=True)
        self.assertTrue(snapshot(self.root).startswith('BLOCKED:'))
        self.assertEqual(list(outside.iterdir()),[])
    def test_hook_source_change_requires_new_native_definition(self):
        from hooks import definitions,generate
        generate(self.root)
        before=definitions(self.root,'codex')
        path=self.root/'scripts/office/state.py'
        path.write_text(path.read_text()+'\n# synthetic update\n')
        self.assertNotEqual(before,definitions(self.root,'codex'))
        with self.assertRaises(ValueError):generate(self.root,check=True)
        generate(self.root)
        generate(self.root,check=True)
    def test_existing_exact_executable_gate_is_verified_without_rewrite(self):
        from unittest.mock import patch
        from bootstrap import install_gate,SHIM
        self.git('init','-q')
        self.assertEqual(install_gate(self.root),'PASS')
        hook=self.root/'.git/hooks/pre-push'
        before=hook.stat().st_ino
        # Models cannot write .git in workspace-write; an installed gate only needs reading.
        with patch('bootstrap.atomic_write',side_effect=PermissionError('synthetic .git read-only')):
            self.assertEqual(install_gate(self.root),'PASS')
        self.assertEqual(hook.read_text(),SHIM)
        self.assertEqual(hook.stat().st_ino,before)
        hook.chmod(0o600)
        with patch('bootstrap.atomic_write',side_effect=PermissionError('synthetic .git read-only')):
            self.assertEqual(install_gate(self.root),'BLOCKED:install-failed')
