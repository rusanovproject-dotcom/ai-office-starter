import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class OfficeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='office-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'офис с пробелами'
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns('.git', '__pycache__', 'docs', 'dist', '.pytest_cache'))

    def put(self, name, value):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value, encoding='utf-8')
        return p

    def hook(self, name, *args, stdin='{}'):
        return subprocess.run(['bash', str(self.root / '.claude/hooks' / name), *map(str, args)], cwd=self.root,
                              env={**os.environ, 'CLAUDE_PROJECT_DIR': str(self.root)}, input=stdin,
                              text=True, capture_output=True)
