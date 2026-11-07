import json
from pathlib import Path
import subprocess
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/office'))
from helpers import OfficeTest

class Package(OfficeTest):
    def test_clean_zip_extraction_bootstrap_and_hidden_paths(self):
        from package import package
        target=self.root.parent/'candidate.zip'
        self.put('.env','synthetic not for export')
        package(self.root,target,candidate=True)
        extracted=self.root.parent/'распаковка с пробелами'
        with zipfile.ZipFile(target) as z:
            names=z.namelist()
            self.assertIn('ai-office-starter/.claude/settings.json',names)
            self.assertIn('ai-office-starter/.codex/hooks.json',names)
            self.assertFalse(any('/.env' in n or '/.git/' in n or '/tests/' in n or '/docs/' in n or 'snapshots/' in n or 'auth.json' in n for n in names))
            self.assertFalse(any((info.external_attr>>16)&0o170000==0o120000 for info in z.infolist()))
            z.extractall(extracted)
        office=extracted/'ai-office-starter'
        p=subprocess.run([sys.executable,str(office/'scripts/office/bootstrap.py')],cwd=office/'me',text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('SKIPPED:not-git',p.stdout)
        p=subprocess.run([sys.executable,str(office/'scripts/office/manifest.py')],cwd=office,text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)

    def test_missing_native_config_is_not_a_valid_package(self):
        from package import package
        from common import write_json
        from manifest import build_manifest
        spec=json.loads((self.root/'.office/release-paths.json').read_text())
        spec['paths'].remove('.claude/settings.json')
        write_json(self.root/'.office/release-paths.json',spec)
        write_json(self.root/'.office/template-manifest.json',build_manifest(self.root))
        with self.assertRaises(ValueError):package(self.root,self.root.parent/'bad.zip',candidate=True)

    def test_owner_data_and_symlinks_are_not_shipped(self):
        from package import package
        self.put('me/profile.md','synthetic profile')
        with self.assertRaises(ValueError):package(self.root,self.root.parent/'personal.zip',candidate=True)
        (self.root/'me/profile.md').unlink()
        path=self.root/'guide/README.md'
        original=self.root.parent/'original';original.write_bytes(path.read_bytes())
        path.unlink();path.symlink_to(original)
        with self.assertRaises(ValueError):package(self.root,self.root.parent/'link.zip',candidate=True)

    def test_release_requires_current_acceptance(self):
        from package import package
        with self.assertRaises(ValueError):package(self.root,self.root.parent/'release.zip')
        report=self.put('acceptance-fixture.json',json.dumps({'overall':'PASS_WITH_SKIPS','source_manifest_sha256':'stale','blockers':[],'checks':[]}))
        with self.assertRaises(ValueError):package(self.root,self.root.parent/'release.zip',acceptance_report=report)
