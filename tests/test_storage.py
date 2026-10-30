import json
from pathlib import Path

import pytest

from rg2019 import storage
from rg2019.media import sha256_file


@pytest.fixture
def transport(tmp_path):
    source, target, scratch = [tmp_path / n for n in ('source', 'target', 'scratch')]
    for p in (source, target, scratch): p.mkdir()
    records = {}
    for role in ('mom', 'child'):
        path = source / '000001' / 'delivery' / (role + '1.avi')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'invented input')
        records[role] = dict(path='delivery/' + path.name, size=path.stat().st_size, sha256=sha256_file(path))
    job = dict(participant='000001', session='delivery', game=1, fingerprint='a' * 64,
               status='Authorized', sources=records)
    out = scratch / 'outputs'
    out.mkdir()
    for name in storage.OUTPUTS: (out / name).write_bytes(b'invented output')
    return storage.Inputs(source), storage.Results(target), scratch, job, out


def test_copy_verified_and_raw_always_blocked(transport):
    inputs, _, scratch, job, _ = transport
    dst = inputs.copy_pair(job, scratch / 'pair', max_bytes=1000, reserve_bytes=1000)
    assert (dst / 'mom.avi').read_bytes() == b'invented input'
    with pytest.raises(FileExistsError):
        inputs.copy_pair(job, scratch / 'pair', max_bytes=1000, reserve_bytes=1000)
    with pytest.raises(PermissionError, match='RAW'):
        inputs.ingest_raw()


@pytest.mark.parametrize('path', ['../secret', '/absolute', 'C:/mapped', 'a\\b', 'NUL.avi', 'a./b', 'a//b'])
def test_nonportable_paths_blocked(path):
    with pytest.raises(ValueError): storage.relative(path)


@pytest.mark.parametrize('point', ['copied:mom.mp4', 'before_commit', 'after_commit'])
def test_disconnect_and_retry(transport, point):
    _, results, _, job, out = transport
    def disconnect(stage):
        if stage == point: raise OSError('simulated SMB disconnect')
    with pytest.raises(OSError):
        results.publish(job, out, {'fixture': True}, checkpoint=disconnect)
    ready = results.inspect(job)
    assert bool(ready) == (point == 'after_commit')
    final = results.publish(job, out, {'fixture': True})
    assert results.inspect(job) == final
    assert results.publish(job, out, {'fixture': True}) == final


def test_conflict_never_overwrites(transport):
    _, results, _, job, out = transport
    with pytest.raises(ValueError, match='blocked'):
        results.publish(dict(job, status='Blocked'), out, {})
    final = results.publish(job, out, {})
    (out / 'mom.mp4').write_bytes(b'different output')
    with pytest.raises(storage.Conflict): results.publish(job, out, {})
    assert (final / 'mom.mp4').read_bytes() == b'invented output'
    (final / 'child.mp4').write_bytes(b'corrupted externally')
    with pytest.raises(storage.Conflict): results.inspect(job)


def test_torn_commit_is_never_treated_as_ready(transport):
    _, results, _, job, out = transport
    slot = results.slot(job)
    slot.mkdir(parents=True)
    (slot / 'COMMITTED.json').write_text('{')
    with pytest.raises(storage.Conflict, match='review'):
        results.publish(job, out, {})
    assert (slot / 'COMMITTED.json').read_text() == '{'


def test_source_mutation_during_copy_rejected(transport, monkeypatch):
    inputs, _, scratch, job, _ = transport
    original = storage.sha256_file
    def change_after_copy(path):
        if Path(path).parent.name == 'pair':
            inputs.path('000001/' + job['sources']['mom']['path']).write_bytes(b'changed data!!')
        return original(path)
    monkeypatch.setattr(storage, 'sha256_file', change_after_copy)
    with pytest.raises(ValueError, match='integrity'):
        inputs.copy_pair(job, scratch / 'pair', max_bytes=1000, reserve_bytes=1000)


def test_space_and_input_overlap_blocked(transport, monkeypatch):
    inputs, results, scratch, job, out = transport
    with pytest.raises(ValueError, match='overlaps'):
        inputs.copy_pair(job, inputs.root / 'scratch', max_bytes=1000, reserve_bytes=1000)
    monkeypatch.setattr(storage.shutil, 'disk_usage', lambda _: type('Disk', (), {'free': 0})())
    with pytest.raises(OSError, match='space'):
        inputs.copy_pair(job, scratch / 'pair', max_bytes=1000, reserve_bytes=1000)
    with pytest.raises(OSError, match='space'):
        results.publish(job, out, {})


def test_marker_cannot_traverse(transport):
    _, results, _, job, _ = transport
    slot = results.slot(job)
    slot.mkdir(parents=True)
    (slot / 'COMMITTED.json').write_text(json.dumps(dict(attempt='../elsewhere', manifest_sha256='a')))
    with pytest.raises(storage.Conflict): results.inspect(job)


def test_concurrent_publish_uses_one_verified_commit(transport):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    _, results, _, job, out = transport
    slot = results.slot(job)
    slot.mkdir(parents=True)
    storage.write_new(slot / 'intent.json', job)
    barrier = Barrier(2)
    def checkpoint(point):
        if point == 'before_commit': barrier.wait(timeout=10)
    def publish():
        try:
            return results.publish(job, out, {}, checkpoint=checkpoint)
        except storage.Conflict:
            # A client may observe the winning marker before it is fully written.
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: publish(), range(2)))
    final = results.inspect(job)
    assert final and any(v == final for v in values)
    assert all(v is None or v == final for v in values)


def test_ordinary_unc_lexical_detection_without_network():
    import os
    from pathlib import PureWindowsPath
    path = PureWindowsPath(r'\\fictional-host\synthetic-share\FOLLOWUP_TEST\00_INBOX')
    assert storage.is_unc(path)
    assert path.drive == r'\\fictional-host\synthetic-share'
    assert (path / '000001' / 'delivery' / 'mother1.avi').name == 'mother1.avi'
    if os.name == 'nt':
        assert storage.validate_root(path) == Path(path)
    else:
        with pytest.raises(ValueError, match='requires Windows'):
            storage.validate_root(path)
