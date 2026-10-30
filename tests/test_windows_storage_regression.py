"""Portable regressions from the non-admin Dell; no policy changes or NAS."""
import base64
import errno
import json
from pathlib import Path

import pytest

from rg2019 import storage, preproduction as pp
from rg2019.fs_errors import check_path, PathBudgetError, SourceChanged, IntegrityError, error_info
from test_storage import transport
from test_preproduction import integrated, execute


def test_compact_full_identity_long_root(transport, tmp_path):
    _, _, _, job, out = transport
    # Absolute result root of >=125 units; v1 would exceed 324 for manifest.
    root = tmp_path / ('roots-' + 'x' * max(1, 125 - len(str(tmp_path)) - 7))
    root.mkdir()
    results = storage.Results(root)
    before = {p: p.read_bytes() for p in out.iterdir()}
    finals = []
    for participant, session, game in [('000001', 'delivery/a/á', 1),
                                       ('000001', 'delivery/a/á', 2),
                                       ('000002', 'delivery/b', 1)]:
        j = dict(job, participant=participant, session=session, game=game)
        final = results.publish(j, out, {'commit': 'fixture'})
        assert results.publish(j, out, {}) == final
        assert results.inspect(j) == final
        manifest = json.loads((final / 'manifest.json').read_text())
        assert manifest['job'] == j and manifest['qc_status'] == 'NotApproved'
        assert manifest['provenance'] == {'commit': 'fixture'}
        assert len(final.parent.name) == 52 and len(final.name) == 28
        assert len(base64.b32decode(final.parent.name.upper() + '====')) == 32
        assert len(str(final / 'manifest.json').encode('utf-16-le')) // 2 <= 259
        finals.append(final)
    assert len(set(finals)) == 3
    assert before == {p: p.read_bytes() for p in out.iterdir()}


@pytest.mark.parametrize('committed', [False, True])
def test_forced_identity_collision_fails_closed(transport, monkeypatch, committed):
    _, results, _, job, out = transport
    monkeypatch.setattr(storage.Results, 'identity_key', staticmethod(lambda _: 'a' * 52))
    if committed:
        results.publish(job, out, {})
    else:
        slot = results.slot(job); slot.mkdir(parents=True)
        storage.write_new(slot / 'intent.json', job)
    before = {p: p.read_bytes() for p in results.root.rglob('*') if p.is_file()}
    with pytest.raises(storage.Conflict, match='identity'):
        results.publish(dict(job, session='different session'), out, {})
    assert before == {p: p.read_bytes() for p in results.root.rglob('*') if p.is_file()}


def test_legacy_prefix_blocks_even_when_v2_exists(transport):
    _, results, _, job, out = transport
    results.publish(job, out, {})
    legacy = results.root / job['participant']; legacy.mkdir()
    (legacy / 'evidence').write_bytes(b'old result must stay')
    before = {p: p.read_bytes() for p in results.root.rglob('*') if p.is_file()}
    for fn in (lambda: results.inspect(job), lambda: results.publish(job, out, {})):
        with pytest.raises(storage.Conflict, match='legacy layout'): fn()
    assert before == {p: p.read_bytes() for p in results.root.rglob('*') if p.is_file()}


def test_unknown_manifest_layout_is_not_reused(transport):
    _, results, _, job, out = transport
    final = results.publish(job, out, {})
    mp = final / 'manifest.json'; m = json.loads(mp.read_text()); m['layout'] = 'future'
    mp.write_text(json.dumps(m))
    marker = results.slot(job) / 'COMMITTED.json'
    record = json.loads(marker.read_text()); record['manifest_sha256'] = storage.sha256_file(mp)
    marker.write_text(json.dumps(record))
    with pytest.raises(storage.Conflict): results.inspect(job)


@pytest.mark.parametrize('directory,limit', [(True, 247), (False, 259)])
def test_utf16_budget_boundaries(tmp_path, directory, limit):
    prefix = str(tmp_path.absolute())
    path = tmp_path / ('x' * (limit - len(prefix) - 1))
    check_path(path, directory=directory)
    with pytest.raises(PathBudgetError, match='shorter'):
        check_path(path.with_name(path.name + 'x'), directory=directory)
    # An astral character occupies two UTF-16 units, not one.
    with pytest.raises(PathBudgetError):
        check_path(path.with_name(path.name[:-1] + '\U0001f600'), directory=directory)


def test_publication_preflight_leaves_no_attempt_or_intent(transport, tmp_path):
    _, _, _, job, out = transport
    root = tmp_path / ('x' * 100) / ('y' * 100)  # deliberately impossible, not created
    with pytest.raises(PathBudgetError): storage.Results(root).publish(job, out, {})
    assert not root.exists()


def test_worker_never_starts_if_publication_budget_fails(integrated, monkeypatch):
    monkeypatch.setattr(storage.Results, 'preflight', lambda *a: (_ for _ in ()).throw(
        PathBudgetError(errno.ENAMETOOLONG, 'fixture path too long')))
    with pytest.raises(PathBudgetError): execute(integrated)
    assert not integrated[4]
    assert not list(Path(integrated[0].workspace).joinpath('scratch').iterdir())
    assert not list(Path(integrated[0].workspace).joinpath('state').glob('*.json'))


@pytest.mark.parametrize('exc,kind', [(PathBudgetError(), 'path_too_long'),
    (PermissionError(), 'access_denied'), (FileExistsError(), 'already_exists'),
    (SourceChanged(), 'source_changed'), (IntegrityError(), 'integrity_error'),
    (OSError(errno.ECONNRESET, 'fixture disconnect'), 'transient_io'),
    (FileNotFoundError(errno.ENOENT, 'not automatically a disconnect'), 'operational_error')])
def test_storage_error_categories(exc, kind):
    assert error_info(exc)['kind'] == kind
    assert error_info(exc)['retryable'] == (kind == 'transient_io')


def test_permanent_error_does_not_consume_retries(integrated, monkeypatch):
    def deny(*a, **k): raise PermissionError('fixture denied')
    monkeypatch.setattr(pp.Inputs, 'copy_pair', deny)
    with pytest.raises(PermissionError): execute(integrated)
    for _ in range(2):
        with pytest.raises(pp.Blocked, match='review'): execute(integrated)
    state = json.loads(next(Path(integrated[0].workspace).joinpath('state').glob('*.json')).read_text())
    assert state['attempts'] == 1 and state['technical_status'] == 'ReviewRequired'
    assert not integrated[4]


def test_path_error_is_not_the_injected_disconnect(transport, monkeypatch):
    _, results, _, job, out = transport
    visited = []
    monkeypatch.setattr(storage.Results, 'preflight', lambda *a: (_ for _ in ()).throw(
        PathBudgetError(errno.ENAMETOOLONG, 'real path error')))
    with pytest.raises(PathBudgetError, match='real path'):
        results.publish(job, out, {}, checkpoint=visited.append)
    assert visited == []


def test_copy_integrity_error_preserves_original(transport, monkeypatch):
    inputs, _, scratch, job, _ = transport
    original_hash = storage.sha256_file
    monkeypatch.setattr(storage, 'sha256_file', lambda p: '0' * 64
                        if Path(p).parent.name == 'pair' else original_hash(p))
    with pytest.raises(IntegrityError, match='copy integrity'):
        inputs.copy_pair(job, scratch / 'pair', max_bytes=1000, reserve_bytes=1000)
    for record in job['sources'].values():
        assert original_hash(inputs.path('000001/' + record['path'])) == record['sha256']


def test_transient_error_manual_recovery_reuses_outputs(integrated):
    visited = []
    def interrupt(point):
        if point == 'before_commit':
            visited.append(point)
            raise ConnectionResetError(errno.ECONNRESET, 'fixture connection reset')
    with pytest.raises(ConnectionResetError): execute(integrated, checkpoint=interrupt)
    state_path = next(Path(integrated[0].workspace).joinpath('state').glob('*.json'))
    state = json.loads(state_path.read_text())
    assert visited == ['before_commit'] and state['last_error']['kind'] == 'transient_io'
    assert state['attempts'] == 1  # no automatic retry
    final = execute(integrated)
    assert final.exists() and len(integrated[4]) == 1
    assert json.loads(state_path.read_text())['qc_status'] == 'NotApproved'


def test_workspace_budget_checked_before_creation(tmp_path):
    root = tmp_path / ('x' * 180)
    with pytest.raises(PathBudgetError): pp.initialize(root)
    assert not root.exists()
