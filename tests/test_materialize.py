import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'scripts/office'))
from helpers import OfficeTest

class Materialization(OfficeTest):
    def test_repeat_and_user_neighbor(self):
        from materialize import materialize
        self.put('.claude/skills/custom/SKILL.md', 'user skill')
        materialize(self.root)
        before = (self.root / '.office/skills-manifest.json').read_bytes()
        materialize(self.root)
        self.assertEqual(before, (self.root / '.office/skills-manifest.json').read_bytes())
        self.assertEqual((self.root / '.claude/skills/custom/SKILL.md').read_text(), 'user skill')

    def test_modified_generated_skill_conflict(self):
        from materialize import materialize
        materialize(self.root)
        self.put('.claude/skills/office-build/SKILL.md', 'user edited built-in')
        with self.assertRaises(ValueError):
            materialize(self.root)
        self.assertEqual((self.root / '.claude/skills/office-build/SKILL.md').read_text(), 'user edited built-in')

    def test_first_migration_conflict_preserves_both(self):
        from materialize import materialize
        (self.root / '.office/skills-manifest.json').unlink(missing_ok=True)
        original = (self.root / '.agents/skills/office-build/SKILL.md').read_bytes()
        self.put('.claude/skills/office-build/SKILL.md', 'legacy user edits')
        with self.assertRaises(ValueError):
            materialize(self.root)
        self.assertEqual((self.root / '.agents/skills/office-build/SKILL.md').read_bytes(), original)

    def test_external_source_symlink_rejected(self):
        from materialize import materialize
        import shutil
        outside=self.root.parent/'private';outside.mkdir()
        (outside/'private-skill').mkdir()
        (outside/'private-skill/SKILL.md').write_text('private synthetic')
        shutil.rmtree(self.root/'.agents/skills')
        (self.root/'.agents/skills').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ValueError):materialize(self.root)
        self.assertFalse((self.root/'.claude/skills/private-skill').exists())
    def test_missing_or_empty_canonical_tree_keeps_generated(self):
        from materialize import materialize
        import shutil
        materialize(self.root)
        path=self.root/'.claude/skills/office-build/SKILL.md'
        before=path.read_bytes()
        shutil.rmtree(self.root/'.agents/skills')
        with self.assertRaises(ValueError):materialize(self.root)
        self.assertEqual(path.read_bytes(),before)
        (self.root/'.agents/skills').mkdir()
        with self.assertRaises(ValueError):materialize(self.root)
        self.assertEqual(path.read_bytes(),before)
