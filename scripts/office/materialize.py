"""Materialize Claude skills from the canonical .agents tree, without symlinks."""
import argparse
from common import ROOT, atomic_write, digest, lock, read_json, safe_path, write_json

def materialize(root, check=False):
    with lock(root, 'skills'):
        manifest = root / '.office/skills-manifest.json'
        old = read_json(manifest, {'version': 1, 'files': {}})['files']
        files = {}
        source = safe_path(root, '.agents/skills')
        if not source.is_dir() or not any(source.glob('*/SKILL.md')):
            raise ValueError('Канонические навыки отсутствуют; производные сохранены')
        if source.is_symlink():
            raise ValueError('Symlink канонического источника навыков запрещён')
        for path in sorted(source.rglob('*')):
            if path.is_symlink():
                raise ValueError('Symlink навыка не поддерживается: ' + str(path))
            if path.is_file() and '__pycache__' not in path.parts:
                rel = '.claude/skills/' + path.relative_to(source).as_posix()
                files[rel] = path.read_bytes()
        conflicts = []
        for rel, data in files.items():
            dst = safe_path(root, rel)
            if dst.exists() and dst.read_bytes() != data:
                if rel not in old or digest(dst.read_bytes()) != old[rel]:
                    conflicts.append(rel)
        for rel, sha in old.items():
            dst = safe_path(root, rel)
            if rel not in files and dst.exists() and digest(dst.read_bytes()) != sha:
                conflicts.append(rel)
        if conflicts:
            raise ValueError('Конфликт производных навыков; обе версии сохранены. Сравните .agents и .claude: ' + ', '.join(conflicts))
        expected = {'version': 1, 'files': {rel: digest(data) for rel, data in files.items()}}
        if check:
            if read_json(manifest) != expected or any(not (root / rel).is_file() or (root / rel).read_bytes() != data for rel, data in files.items()):
                raise ValueError('Материализация устарела')
            return expected
        for rel, data in files.items():
            if not (root / rel).exists() or (root / rel).read_bytes() != data:
                atomic_write(safe_path(root, rel), data)
        for rel in old.keys() - files.keys():
            safe_path(root, rel).unlink(missing_ok=True)
        write_json(manifest, expected)
        return expected

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        materialize(ROOT, args.check)
        print('skills=ok')
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, str(exc) + '\n')
