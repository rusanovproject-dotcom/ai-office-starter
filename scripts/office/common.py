"""Shared file operations. No dependencies outside Python's standard library."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    binary = isinstance(data, bytes)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb' if binary else 'w', **({} if binary else {'encoding': 'utf-8', 'newline': '\n'})) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n')

def safe_path(root, relative):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise ValueError('Недопустимый путь: ' + str(relative))
    result = root / p
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError('Путь выходит за пределы офиса: ' + str(relative))
    return result

@contextmanager
def lock(root, name='office', timeout=15):
    """Portable mkdir lock. A stale lock is diagnosed, never silently stolen."""
    folder = safe_path(root, '.office/' + name + '.lock')
    folder.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            folder.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError('Офис занят или остался lock после сбоя: ' + str(folder))
            time.sleep(.03)
    try:
        yield
    finally:
        folder.rmdir()

def is_secret_path(relative):
    """Classify every path component, not just the file basename."""
    path=Path(relative)
    for component in path.parts:
        name=component.casefold()
        if name.startswith(('.env','service-account','id_rsa','id_dsa','id_ecdsa','id_ed25519')):
            return True
        if name in ('secrets','credentials','config.env','.netrc','.pgpass','.envrc') or name.startswith(('secrets.','credentials.')):
            return True
    return path.suffix.casefold() in ('.pem','.key')
