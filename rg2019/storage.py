"""Filesystem transport for UNC-capable Windows and local synthetic doubles.

No credential handling, drive mapping, RAW ingestion, destructive cleanup or
claim that SMB implements local locking/rename semantics. Readers MUST inspect
the commit record and content hashes; directory visibility is not publication.
"""
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import uuid

from .media import sha256_file
from .synthetic_plan import contained, digest

OUTPUTS = {'mom.mp4', 'child.mp4', 'sync.json'}


class Conflict(ValueError):
    """Existing immutable data differs or an indeterminate commit needs review."""


def relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('expected portable relative path')
    for part in value.split('/'):
        if (part in ('', '.', '..') or part.endswith((' ', '.')) or
                re.search(r'[<>"|?*\x00-\x1f]', part) or
                part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                    *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}):
            raise ValueError('unsafe Windows-compatible relative path')
    return value


def is_unc(value):
    return str(value).startswith(('\\\\', '//'))


def validate_root(value):
    """Lexical check only: construction never connects to storage."""
    if is_unc(value):
        win = PureWindowsPath(value)
        if not win.drive.startswith('\\\\') or not win.root or '..' in win.parts or str(value).startswith(('\\\\?\\', '\\\\.\\')):
            raise ValueError('expected ordinary UNC server/share path')
        if os.name != 'nt':
            raise ValueError('native UNC transport requires Windows; use local doubles here')
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or path == Path(path.anchor):
        raise ValueError('dedicated absolute storage root required')
    return path


def write_new(path, value):
    with open(path, 'x', encoding='utf-8') as handle:
        json.dump(value, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())


def verified_copy(src, dst, expected, *, max_bytes):
    """Exclusive destination, bounded copy and independent source recheck."""
    before = src.stat()
    if before.st_size != expected['size'] or before.st_size > max_bytes:
        raise ValueError('input size changed or exceeds limit')
    count = 0
    with open(src, 'rb') as source, open(dst, 'xb') as target:
        while chunk := source.read(1024 * 1024):
            count += len(chunk)
            if count > max_bytes or count > expected['size']:
                raise ValueError('input grew during ingestion')
            target.write(chunk)
        target.flush()
        os.fsync(target.fileno())
    after = src.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or (
            count != expected['size'] or sha256_file(dst) != expected['sha256'] or
            sha256_file(src) != expected['sha256']):
        raise ValueError('copy/source integrity mismatch')


class Inputs:
    """Read-only capability; no rename, delete or write operation exists."""
    def __init__(self, root):
        self.root = validate_root(root)

    def path(self, rel):
        return contained(self.root, self.root / relative(rel))

    def copy_pair(self, job, destination, *, max_bytes, reserve_bytes):
        if job['status'] != 'Authorized' or set(job['sources']) != {'mom', 'child'}:
            raise ValueError('blocked or invalid pair')
        destination = validate_root(destination)
        contained(destination, destination)
        if destination.is_relative_to(self.root) or self.root.is_relative_to(destination):
            raise ValueError('scratch overlaps protected input')
        total = sum(r['size'] for r in job['sources'].values())
        if total > max_bytes:
            raise ValueError('input byte limit exceeded')
        if shutil.disk_usage(destination.parent).free < total * 20 + reserve_bytes:
            raise OSError('insufficient scratch space')
        destination.mkdir(exist_ok=False)
        for role, record in job['sources'].items():
            src = self.path(job['participant'] + '/' + relative(record['path']))
            verified_copy(src, destination / (role + '.avi'), record, max_bytes=max_bytes)
        return destination

    def ingest_raw(self, *args, **kwargs):
        raise PermissionError('RAW ingestion blocked pending approved immutable-originals mechanism')


class Results:
    """Immutable attempts plus exclusive completion record, no remote lock/rename.

    Requires server support for exclusive create, verified in future SMB validation.
    Torn completion/intent records block; never auto-steal or overwrite them.
    Abandoned attempts are retained. No retry loop inside the transport.
    """
    def __init__(self, root):
        self.root = validate_root(root)

    def path(self, rel):
        return contained(self.root, self.root / relative(rel))

    def slot(self, job):
        if not re.fullmatch(r'\d{6}', job['participant']) or type(job['game']) is not int or job['game'] < 1:
            raise ValueError('invalid job identity')
        if not re.fullmatch(r'[0-9a-f]{64}', job['fingerprint']) or not job['session']:
            raise ValueError('invalid session/fingerprint')
        return self.path(f"{job['participant']}/{digest(job['session'])}/game-{job['game']}/{job['fingerprint']}")

    def inspect(self, job):
        slot = self.slot(job)
        marker = contained(self.root, slot / 'COMMITTED.json')
        if not marker.exists():
            return None
        try:
            record = json.loads(marker.read_text(encoding='utf-8'))
            if set(record) != {'attempt', 'manifest_sha256'} or not re.fullmatch(r'attempt-[0-9a-f]{32}', record['attempt']):
                raise Conflict('invalid completion record')
            attempt = contained(self.root, slot / record['attempt'])
            mp = contained(self.root, attempt / 'manifest.json')
            if sha256_file(mp) != record['manifest_sha256']:
                raise Conflict('manifest hash conflict')
            manifest = json.loads(mp.read_text(encoding='utf-8'))
            if manifest['job'] != job or set(manifest['files']) != OUTPUTS:
                raise Conflict('publication provenance conflict')
            if {p.name for p in attempt.iterdir()} != OUTPUTS | {'manifest.json'}:
                raise Conflict('unexpected publication file set')
            for name, expected in manifest['files'].items():
                p = contained(self.root, attempt / name)
                if p.stat().st_size != expected['size'] or sha256_file(p) != expected['sha256']:
                    raise Conflict('publication content conflict')
            return attempt
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise Conflict('indeterminate completion requires human review') from exc

    def publish(self, job, outputs, provenance, *, checkpoint=lambda _: None):
        outputs = Path(outputs).absolute()
        records = {name: dict(size=contained(outputs, outputs / name).stat().st_size,
                              sha256=sha256_file(outputs / name)) for name in OUTPUTS}
        existing = self.inspect(job)
        if existing:
            if any(sha256_file(existing / n) != r['sha256'] for n, r in records.items()):
                raise Conflict('divergent existing result')
            return existing
        if shutil.disk_usage(self.root).free < sum(r['size'] for r in records.values()) + 1024**2:
            raise OSError('insufficient publication space')
        slot = self.slot(job)
        slot.mkdir(parents=True, exist_ok=True)
        intent = contained(self.root, slot / 'intent.json')
        try:
            write_new(intent, job)
        except FileExistsError:
            try:
                if json.loads(intent.read_text(encoding='utf-8')) != job:
                    raise Conflict('reserved identity conflict')
            except json.JSONDecodeError as exc:
                raise Conflict('incomplete intent requires review') from exc
        attempt = contained(self.root, slot / ('attempt-' + uuid.uuid4().hex))
        attempt.mkdir()
        for name, expected in records.items():
            verified_copy(outputs / name, attempt / name, expected, max_bytes=expected['size'])
            checkpoint('copied:' + name)
        manifest = dict(schema='rg2019.publication.v1', job=job, files=records,
                        provenance=provenance, technical_status='TechnicalSuccess', qc_status='NotApproved')
        write_new(attempt / 'manifest.json', manifest)
        checkpoint('before_commit')
        try:
            write_new(contained(self.root, slot / 'COMMITTED.json'), dict(
                attempt=attempt.name, manifest_sha256=sha256_file(attempt / 'manifest.json')))
        except FileExistsError:
            # Concurrent writer may still be writing: fail closed if unreadable.
            pass
        checkpoint('after_commit')
        final = self.inspect(job)
        if not final or any(sha256_file(final / n) != r['sha256'] for n, r in records.items()):
            raise Conflict('concurrent publication conflict')
        return final
