import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/office'))
from helpers import OfficeTest,ROOT

class State(OfficeTest):
    def test_concurrent_merges(self):
        code="import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from state import update;update(Path(sys.argv[2]),{sys.argv[3]:sys.argv[3]})"
        jobs=[subprocess.Popen([sys.executable,'-c',code,str(ROOT/'scripts/office'),str(self.root),f'k{i}']) for i in range(8)]
        for job in jobs:self.assertEqual(job.wait(),0)
        from common import read_json
        self.assertEqual(len(read_json(self.root/'.office/state.json')),8)
