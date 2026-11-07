import os
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/office'))
from helpers import OfficeTest

class PrivacyGate(OfficeTest):
    def setUp(self):
        super().setUp()
        # Git objects contain only explicitly named synthetic files.
        self.env={**os.environ,'GIT_CONFIG_GLOBAL':os.devnull,'GIT_CONFIG_NOSYSTEM':'1'}
        self.git('init','-q')
        self.git('config','user.name','Synthetic Test')
        self.git('config','user.email','synthetic@example.invalid')
    def git(self,*args):
        p=subprocess.run(['git',*args],cwd=self.root,env=self.env,text=True,capture_output=True)
        if p.returncode:raise RuntimeError(p.stderr)
        return p.stdout.strip()
    def commit(self,path,value):
        self.put(path,value)
        self.git('add','--',path)
        self.git('commit','-qm','synthetic')
        return self.git('rev-parse','HEAD')
    def refs(self,sha):return f'refs/heads/main {sha} refs/heads/main '+('0'*40)+'\n'
    def test_private_unknown_and_secret_history(self):
        from privacy_gate import check
        sha=self.commit('clients/test/README.md','# Synthetic customer\n')
        with self.assertRaises(ValueError):check(self.root,self.refs(sha),'unknown',private_check=lambda _:False)
        self.assertEqual(check(self.root,self.refs(sha),'synthetic',private_check=lambda _:True),'PASS:pre-push-history')
        self.commit('note.txt','token='+ 'sk-'+'A'*40)
        sha=self.commit('note.txt','secret removed')
        with self.assertRaises(ValueError):check(self.root,self.refs(sha),'synthetic',private_check=lambda _:True)
    def test_zero_sha_deletion_and_unreadable_history(self):
        from privacy_gate import check
        self.assertEqual(check(self.root,self.refs('0'*40),'unknown',private_check=lambda _:False),'PASS:pre-push-history')
        with self.assertRaises(ValueError):check(self.root,self.refs('a'*40),'unknown')
    def test_metadata_and_unmanifested_personal_root_are_private(self):
        from privacy_gate import check
        self.put('.gitignore','')
        for path in ('clients/INDEX.md','AGENTS.md','secrets/payment.json'):
            sha=self.commit(path,'Synthetic personal detail' if not path.endswith('.json') else '{"password":"synthetic"}')
            with self.assertRaises(ValueError):check(self.root,self.refs(sha),'unknown',private_check=lambda _:False)
    def test_existing_credential_formats_remain_blocked(self):
        from privacy_gate import check
        samples=['sk-'+'b'*16, 'eyJ'+'A'*16+'.'+'B'*20+'.'+'C'*12,
                 'postgresql'+'://demo:example-password@localhost/db',
                 'https://hooks.'+'slack.com/services/'+'A'*25]
        for index,value in enumerate(samples):
            repo=self.root.parent/('format-'+str(index));repo.mkdir()
            def git(*args):
                return subprocess.run(['git','-C',str(repo),*args],env=self.env,text=True,capture_output=True,check=True).stdout.strip()
            git('init','-q');git('config','user.name','Synthetic');git('config','user.email','synthetic@example.invalid')
            (repo/'note.txt').write_text(value)
            git('add','note.txt');git('commit','-qm','synthetic')
            sha=git('rev-parse','HEAD')
            with self.assertRaises(ValueError,msg='format '+str(index)):
                check(repo,self.refs(sha),'synthetic',private_check=lambda _:True)
    def isolated_repo(self,name,path,value,deleted=False):
        repo=self.root.parent/name;repo.mkdir()
        def git(*args):
            return subprocess.run(['git','-C',str(repo),*args],env=self.env,text=True,capture_output=True,check=True).stdout.strip()
        git('init','-q');git('config','user.name','Synthetic');git('config','user.email','synthetic@example.invalid')
        target=repo/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(value)
        git('add','--',path);git('commit','-qm','synthetic')
        if deleted:
            git('rm','--',path);git('commit','-qm','remove synthetic')
        return repo,self.refs(git('rev-parse','HEAD'))
    def test_inbox_owner_data_in_current_and_deleted_history(self):
        from privacy_gate import check
        for deleted in (False,True):
            with self.subTest(deleted=deleted):
                repo,refs=self.isolated_repo('inbox-'+str(deleted),'inbox/import.md','Synthetic owner questionnaire',deleted)
                with self.assertRaises(ValueError):check(repo,refs,'unknown',private_check=lambda _:False)
                self.assertTrue(check(repo,refs,'synthetic',private_check=lambda _:True).startswith('PASS'))
    def test_each_legacy_media_format_blocked_even_in_deleted_history(self):
        from privacy_gate import check
        for extension in ('webm','m4a','oga','aac','flac'):
            for deleted in (False,True):
                with self.subTest(extension=extension,deleted=deleted):
                    repo,refs=self.isolated_repo(extension+str(deleted),'voice.'+extension,'Synthetic media placeholder',deleted)
                    for private in (False,True):
                        with self.assertRaises(ValueError):check(repo,refs,'synthetic',private_check=lambda _:private)
    def test_contextual_hex_credentials_and_clean_hash_controls(self):
        import json
        from privacy_gate import check
        for index,field in enumerate(('api_key','API_KEY','token','secret','password','key')):
            with self.subTest(field=field):
                repo,refs=self.isolated_repo('credential-'+str(index),'notes.json',json.dumps({field:'a1'*24}),deleted=True)
                with self.assertRaises(ValueError):check(repo,refs,'synthetic',private_check=lambda _:True)
        controls=json.dumps({'sha256':'a1'*32,'git_sha':'b'*40,'url':'https://example.invalid/'+'c'*48,'data':'data:application/octet-stream;base64,'+'d'*64})
        repo,refs=self.isolated_repo('clean-hashes','manifest.json',controls)
        self.assertTrue(check(repo,refs,'unknown',private_check=lambda _:False).startswith('PASS'))
