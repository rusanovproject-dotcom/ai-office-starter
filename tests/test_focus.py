from helpers import OfficeTest

class Focus(OfficeTest):
    def test_stale_mit_not_injected(self):
        self.put('team/ops/today.md', '# 2001-01-01\nДата: 2001-01-01\nTimezone: UTC\nMIT: старый синтетический приоритет\n')
        result = self.hook('prompt-inject.sh')
        self.assertNotIn('[focus]', result.stdout)

class Freshness(OfficeTest):
    def test_dates_and_timezone(self):
        import sys
        from pathlib import Path
        from datetime import datetime, timezone
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/office'))
        from state import focus
        now=datetime(2026,11,7,23,30,tzinfo=timezone.utc)
        for value in ['2026-11-06','2026-11-09','bad','']:
            self.put('team/ops/today.md',f'Дата: {value}\nTimezone: UTC\nMIT: x\n')
            self.assertNotIn('[focus]',focus(self.root,now))
        self.put('team/ops/today.md','Дата: 2026-11-08\nTimezone: Asia/Ho_Chi_Minh\nMIT: x\n')
        self.assertIn('[focus]',focus(self.root,now))
        self.put('team/ops/today.md','Дата: 2026-11-07\nTimezone: UTC\nMIT: x\nРежим: тишина\n')
        self.assertNotIn('[focus]',focus(self.root,now))
        self.put('team/ops/today.md','Дата: 2026-11-07\nTimezone: invalid\nMIT: x\n')
        self.assertNotIn('[focus]',focus(self.root,now))
