"""Cooperative, same-volume local publication. No SMB guarantee."""
import json
import os
import shutil
import uuid
from contextlib import contextmanager

from .media import sha256_file
from .synthetic_plan import digest, contained
from .fs_errors import check_path


@contextmanager
def exclusive(path):
    """OS lock automatically released on crash; never steals a live lock."""
    with open(path, 'a+b') as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def destination(box, job):
    # Full identity hash prevents collisions between sessions/games/inputs.
    return box.path('published', digest([job['participant'], job['session'], job['game'], job['fingerprint']]))


def inspect(box, job):
    final = destination(box, job)
    if not final.exists():
        return None
    manifest = json.loads(contained(box.root, final / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('job') != job or set(manifest.get('files', {})) != {'mom.mp4', 'child.mp4', 'sync.json'}:
        raise ValueError('publication provenance conflict')
    if {p.name for p in final.iterdir()} != set(manifest['files']) | {'manifest.json'}:
        raise ValueError('publication file-set conflict')
    for name, record in manifest['files'].items():
        p = contained(box.root, final / name)
        if p.stat().st_size != record['size'] or sha256_file(p) != record['sha256']:
            raise ValueError('publication content conflict')
    return final


def publish(box, job, outputs, before_rename=lambda: None):
    for folder in (destination(box, job), box.path('published', '.stage-' + 'f' * 32)):
        check_path(folder, directory=True)
        for name in ('mom.mp4', 'child.mp4', 'sync.json', 'manifest.json'):
            check_path(folder / name)
    check_path(box.path('state', 'publish.lock'))
    outputs = contained(box.path('scratch'), outputs)
    with exclusive(box.path('state', 'publish.lock')):
        if destination(box, job).exists():
            existing = inspect(box, job)
            for name in ('mom.mp4', 'child.mp4', 'sync.json'):
                if sha256_file(contained(box.root, outputs / name)) != sha256_file(existing / name):
                    raise ValueError('divergent existing result')
            return existing
        total = sum(contained(box.root, outputs / n).stat().st_size for n in ('mom.mp4', 'child.mp4', 'sync.json'))
        if shutil.disk_usage(box.path('published')).free < total + 1024**2:
            raise OSError('insufficient publication space')
        stage = box.path('published', '.stage-' + uuid.uuid4().hex)
        stage.mkdir()
        records = {}
        for name in ('mom.mp4', 'child.mp4', 'sync.json'):
            src = contained(box.root, outputs / name)
            expected = sha256_file(src)
            shutil.copyfile(src, stage / name)
            if sha256_file(stage / name) != expected:
                raise ValueError('staging copy integrity failure')
            records[name] = dict(size=(stage / name).stat().st_size, sha256=expected)
        manifest = dict(schema='synthetic-publication-1', job=job, files=records,
                        processing_status='TechnicalSuccess', qc_status='NotApproved')
        with open(stage / 'manifest.json', 'x', encoding='utf-8') as handle:
            json.dump(manifest, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        before_rename()
        # The staging directory and destination are siblings on one volume.
        os.rename(stage, destination(box, job))
        return inspect(box, job)
