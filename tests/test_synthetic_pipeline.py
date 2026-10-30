"""All inputs are invented fixtures. No network or real scientific paths."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from rg2019.config import from_dict
from rg2019.synthetic_local import Sandbox, process
from rg2019.synthetic_plan import plan, contained
from rg2019.synthetic_publish import publish, inspect, exclusive, destination
from rg2019 import synthetic_run
from helpers import make_video, wall_signal, recording


@pytest.fixture
def case(tmp_path):
    box = Sandbox.create(tmp_path / 'synthetic')
    cfg = from_dict(dict(followup_root=str(box.path('input')), field_sessions={'000001': ['delivery']},
                        sync=dict(max_lag_seconds=5, window_seconds=4, fine_search_seconds=1),
                        encode=dict(preset='ultrafast', crf=30)))
    participant = box.path('input', '00_INBOX', '000001')
    for role in ('mother', 'children'):
        p = participant / 'delivery' / (role + '1.avi')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'invented fixture')
    return box, cfg, participant


def authorized(case):
    box, cfg, _ = case
    blocked = plan(cfg, '000001')[0]
    fp = blocked['fingerprint']
    approvals = {fp: dict(fingerprint=fp, synthetic_only=True, session_reviewed=True,
                         delivery_complete=True, integrity_verified=True,
                         evidence='synthetic fixture contract, not scientific approval')}
    return plan(cfg, '000001', approvals)[0], approvals


def outputs(box):
    out = box.path('scratch', 'fixture-output')
    out.mkdir(exist_ok=True)
    for name in ('mom.mp4', 'child.mp4', 'sync.json'):
        (out / name).write_bytes(b'publication fixture')
    return out


@pytest.mark.parametrize('gate', ['synthetic_only', 'session_reviewed', 'delivery_complete', 'integrity_verified'])
def test_missing_gate_blocks(case, gate):
    job, approvals = authorized(case)
    approvals[job['fingerprint']][gate] = False
    assert gate in plan(case[1], '000001', approvals)[0]['reasons']


@pytest.mark.parametrize('problem', ['incomplete', 'duplicate', 'transfer', 'manifest', 'unknown_session'])
def test_inventory_blocks_even_with_approval(case, problem):
    _, cfg, root = case
    if problem == 'incomplete':
        (root / 'delivery/children1.avi').unlink()
    elif problem == 'duplicate':
        p = root / 'delivery/copy/mother1.avi'
        p.parent.mkdir()
        p.write_bytes(b'duplicate')
    elif problem == 'transfer':
        (root / 'delivery/file.partial').write_bytes(b'partial')
    elif problem == 'manifest':
        (root / 'delivery/copy.json').write_text(json.dumps(dict(schema='rg2019.inventory.v1', files=[])))
    else:
        cfg.field_sessions = {}
        (root / 'delivery/mother1.avi').rename(root / 'mother1.avi')
    job, _ = authorized(case)
    assert job['status'] == 'Blocked'


def test_inferred_session_requires_review(case):
    case[1].field_sessions = {}
    job, approvals = authorized(case)
    approvals[job['fingerprint']]['session_reviewed'] = False
    assert plan(case[1], '000001', approvals)[0]['status'] == 'Blocked'


def test_multisession_determinism_and_stale_inputs(case):
    _, cfg, root = case
    shutil.copytree(root / 'delivery', root / 'second')
    cfg.field_sessions['000001'].append('second')
    first = plan(cfg, '000001')
    assert first == plan(cfg, '000001') and len(first) == 2
    assert first[0]['fingerprint'] != first[1]['fingerprint']
    (root / 'delivery/mother1.avi').write_bytes(b'changed')
    assert first[0]['fingerprint'] != plan(cfg, '000001')[0]['fingerprint']


def test_insufficient_space(case, monkeypatch):
    job, _ = authorized(case)
    monkeypatch.setattr(shutil, 'disk_usage', lambda _: type('Disk', (), {'free': 0})())
    with pytest.raises(OSError, match='space'):
        process(case[0], case[1], job)


@pytest.mark.parametrize('error', [PermissionError('Windows file open'), OSError('simulated SMB disconnect')])
def test_copy_failures_preserve_sources(case, monkeypatch, error):
    job, _ = authorized(case)
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(shutil, 'copyfile', fail)
    with pytest.raises(OSError):
        process(case[0], case[1], job)
    assert (case[2] / 'delivery/mother1.avi').read_bytes() == b'invented fixture'


def test_hung_worker_deadline(case, monkeypatch):
    job, _ = authorized(case)
    original = subprocess.Popen
    def hung(command, **kwargs):
        if 'rg2019.synthetic_worker' not in command:
            return original(command, **kwargs)
        # Simulate extraction/FFmpeg never returning inside the real worker.
        code = ('import time; from pathlib import Path; from types import SimpleNamespace; '
                'from rg2019 import synthetic_worker as w; '
                'w.media.probe=lambda *a: SimpleNamespace(has_video=True, has_audio=True, '
                'duration=40, width=160, height=120, fps=10, audio_start=0); '
                'w.media.extract_audio=lambda *a: (Path(' + repr(command[-1]) +
                ').joinpath("blocked-extraction").write_text("simulated FFmpeg hang"), time.sleep(60))[1]; '
                'w.work(Path(' + repr(command[-1]) + '))')
        return original([sys.executable, '-c', code], **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', hung)
    with pytest.raises(TimeoutError):
        process(case[0], case[1], job, timeout=5)
    assert list(case[0].path('scratch').glob('*/blocked-extraction'))


def test_transaction_interruption_conflict_and_repetition(case):
    box, _, _ = case
    job, _ = authorized(case)
    out = outputs(box)
    def interrupt():
        raise OSError('interrupted before atomic rename')
    with pytest.raises(OSError):
        publish(box, job, out, before_rename=interrupt)
    assert not destination(box, job).exists()
    assert list(box.path('published').glob('.stage-*'))
    final = publish(box, job, out)
    assert publish(box, job, out) == final
    (final / 'mom.mp4').write_bytes(b'divergent')
    with pytest.raises(ValueError, match='conflict'):
        publish(box, job, out)
    assert (final / 'mom.mp4').read_bytes() == b'divergent'


def test_recovery_after_publish_before_journal(case, monkeypatch):
    box, cfg, _ = case
    job, approvals = authorized(case)
    out = outputs(box)
    calls = []
    monkeypatch.setattr(synthetic_run, 'process', lambda *a, **k: calls.append(1) or out)
    def crash():
        raise KeyboardInterrupt('crash after rename')
    with pytest.raises(KeyboardInterrupt):
        synthetic_run.run(box, cfg, '000001', job['fingerprint'], approvals, after_publish=crash)
    assert inspect(box, job)
    final = synthetic_run.run(Sandbox(box.root), cfg, '000001', job['fingerprint'], approvals)
    for _ in range(35):
        assert synthetic_run.run(box, cfg, '000001', job['fingerprint'], approvals) == final
    state = json.loads(box.path('state', job['fingerprint'] + '.json').read_text())
    assert calls == [1] and state['qc_status'] == 'NotApproved'
    assert state['processing_status'] == 'Published' and len(state['history']) == 30


def test_safe_retry_after_transient_copy_failure(case, monkeypatch):
    box, cfg, _ = case
    job, approvals = authorized(case)
    out = outputs(box)
    def fail(*a, **k):
        raise PermissionError('synthetic sharing violation')
    monkeypatch.setattr(synthetic_run, 'process', fail)
    with pytest.raises(PermissionError):
        synthetic_run.run(box, cfg, '000001', job['fingerprint'], approvals)
    monkeypatch.setattr(synthetic_run, 'process', lambda *a, **k: out)
    assert synthetic_run.run(box, cfg, '000001', job['fingerprint'], approvals).exists()


def test_concurrent_execution_excluded(case):
    job, approvals = authorized(case)
    with exclusive(case[0].path('state', 'execution.lock')):
        with pytest.raises(OSError):
            synthetic_run.run(case[0], case[1], '000001', job['fingerprint'], approvals)


def test_retry_budget_is_bounded(case, monkeypatch):
    box, cfg, _ = case
    job, approvals = authorized(case)
    calls = []
    def fail(*a, **k):
        calls.append(1)
        raise OSError('transient simulated disconnect')
    monkeypatch.setattr(synthetic_run, 'process', fail)
    for _ in range(3):
        with pytest.raises(OSError):
            synthetic_run.run(box, cfg, '000001', job['fingerprint'], approvals)
    with pytest.raises(ValueError, match='retry limit'):
        synthetic_run.run(box, cfg, '000001', job['fingerprint'], approvals)
    assert len(calls) == 3


def test_integrity_change_during_copy_blocks(case, monkeypatch):
    job, _ = authorized(case)
    copy = shutil.copyfile
    def corrupt(src, dst):
        copy(src, dst)
        Path(dst).write_bytes(b'corrupted scratch copy')
    monkeypatch.setattr(shutil, 'copyfile', corrupt)
    with pytest.raises(ValueError, match='integrity'):
        process(case[0], case[1], job)


def test_outside_paths_and_stale_approval_rejected(case, tmp_path):
    box, cfg, root = case
    with pytest.raises(ValueError):
        contained(box.root, tmp_path / 'outside')
    job, approvals = authorized(case)
    (root / 'delivery/mother1.avi').write_bytes(b'changed after approval')
    with pytest.raises(ValueError, match='stale'):
        synthetic_run.run(box, cfg, '000001', job['fingerprint'], approvals)
    cfg.inbox = str(tmp_path / 'outside')
    with pytest.raises(ValueError):
        synthetic_run.run(box, cfg, '000001', job['fingerprint'], approvals)


def test_end_to_end_real_synthetic_media(case, monkeypatch):
    box, cfg, root = case
    rate = 16000
    signal = wall_signal(45, rate, seed=729)
    for name, start in [('mother', 0), ('children', 2)]:
        make_video(root / 'delivery' / (name + '1.avi'), recording(signal, rate, start, 40), rate, 40)
    job, approvals = authorized(case)
    before = {p: p.read_bytes() for p in root.rglob('*.avi')}
    final = synthetic_run.run(box, cfg, '000001', job['fingerprint'], approvals)
    assert inspect(box, job) == final
    assert abs(json.loads((final / 'sync.json').read_text())['offset_seconds'] - 2) < 0.15
    def no_reencode(*a, **k):
        pytest.fail('idempotent run attempted encoding')
    monkeypatch.setattr(synthetic_run, 'process', no_reencode)
    assert synthetic_run.run(box, cfg, '000001', job['fingerprint'], approvals) == final
    assert all(p.read_bytes() == content for p, content in before.items())
