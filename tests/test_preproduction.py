import json

import pytest

from rg2019 import preproduction as pp
from rg2019.config import from_dict
from rg2019.delivery import template, delivery_plan
from rg2019.storage import Conflict, OUTPUTS
from rg2019.fs_errors import SourceChanged
from test_delivery_contract import close_fixture


@pytest.fixture
def integrated(tmp_path, monkeypatch):
    root = pp.initialize(tmp_path / 'synthetic')
    cfg = from_dict(dict(followup_root=str(root), field_sessions={'000001': ['delivery']}))
    for role in ('mother', 'children'):
        p = cfg.inbox_dir / '000001' / 'delivery' / (role + '1.avi')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'invented synthetic input')
    declaration = close_fixture(template(cfg, '000001'))
    job = delivery_plan(cfg, '000001', declaration)[0]
    calls = []
    def worker(attempt, timeout):
        calls.append(attempt)
        outputs = attempt / 'outputs'
        outputs.mkdir()
        for name in OUTPUTS: (outputs / name).write_bytes(b'invented result')
        return outputs
    monkeypatch.setattr(pp, 'run_worker', worker)
    monkeypatch.setattr(pp, 'provenance', lambda *a: dict(commit='fixture', tools='double'))
    return pp.Settings(str(root), enabled=True), cfg, declaration, job, calls


def execute(case, **kwargs):
    settings, cfg, declaration, job, _ = case
    return pp.run(settings, cfg, '000001', job['fingerprint'], declaration, **kwargs)


def test_integration_recovery_and_idempotence(integrated):
    def crash(point):
        if point == 'after_commit': raise KeyboardInterrupt('synthetic power loss')
    with pytest.raises(KeyboardInterrupt): execute(integrated, checkpoint=crash)
    final = execute(integrated)
    for _ in range(5): assert execute(integrated) == final
    assert len(integrated[4]) == 1
    manifest = json.loads((final / 'manifest.json').read_text())
    assert manifest['qc_status'] == 'NotApproved'
    assert manifest['provenance']['commit'] == 'fixture'


def test_disconnect_reuses_verified_outputs(integrated):
    def disconnect(point):
        if point == 'before_commit': raise OSError('simulated SMB drop')
    with pytest.raises(OSError, match='simulated SMB drop'): execute(integrated, checkpoint=disconnect)
    assert execute(integrated).exists()
    assert len(integrated[4]) == 1


def test_retry_budget(integrated):
    def fail(point): raise OSError('simulated transient failure')
    for _ in range(3):
        with pytest.raises(OSError, match='simulated transient failure'): execute(integrated, checkpoint=fail)
    with pytest.raises(pp.Blocked, match='budget'): execute(integrated)


def test_default_disabled_and_live_unc_block_before_io(tmp_path):
    with pytest.raises(pp.Blocked, match='disabled'):
        pp.Settings(str(tmp_path)).validate(execute=True)
    with pytest.raises(pp.Blocked, match='UNC'):
        pp.Settings('\\\\fictional-host\\synthetic-share', enabled=True).validate(execute=True)
    with pytest.raises(pp.Blocked):
        pp.Settings(str(tmp_path), enabled=True, mode='production').validate(execute=True)


def test_changed_delivery_after_ingest_blocks(integrated):
    def change(point):
        if point == 'after_ingest':
            (integrated[1].inbox_dir / '000001/delivery/mother1.avi').write_bytes(b'changed')
    with pytest.raises(SourceChanged, match='changed'):
        execute(integrated, checkpoint=change)
    assert not integrated[4]


def test_execution_lock_excludes_second_writer(integrated):
    root = integrated[0].validate()
    with pp.exclusive(root / 'state/execution.lock'):
        with pytest.raises(OSError): execute(integrated)


def test_journal_tampering_blocks(integrated):
    execute(integrated)
    path = integrated[0].validate() / 'state' / (integrated[3]['fingerprint'] + '.json')
    state = json.loads(path.read_text())
    state['events'][0]['detail'] = 'modified'
    path.write_text(json.dumps(state))
    with pytest.raises(Conflict, match='integrity'): execute(integrated)


def test_cli_disabled_exit_code(integrated, tmp_path, capsys):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(dict(execution=dict(workspace=integrated[0].workspace), pipeline={})))
    assert pp.main([str(config), 'run', '--participant', '000001']) == 20
    assert 'disabled' in capsys.readouterr().err


@pytest.mark.parametrize('problem', ['missing_child', 'duplicate', 'typo', 'unknown_json', 'split_cameras'])
def test_discovery_review_cannot_be_overridden(integrated, problem):
    _, cfg, _, _, _ = integrated
    root = cfg.inbox_dir / '000001' / 'delivery'
    if problem == 'missing_child': (root / 'children1.avi').unlink()
    elif problem == 'duplicate':
        (root / 'backup').mkdir()
        (root / 'backup/mother1.avi').write_bytes(b'duplicate fixture')
    elif problem == 'typo': (root / 'mother1.avi').rename(root / 'mohter1.avi')
    elif problem == 'unknown_json': (root / 'copy.json').write_text('{}')
    else:
        for role in ('mother', 'children'):
            (root / role).mkdir()
            (root / (role + '1.avi')).rename(root / role / (role + '1.avi'))
        cfg.field_sessions = {'000001': ['delivery/mother', 'delivery/children']}
    d = close_fixture(template(cfg, '000001'))
    assert all(j['status'] == 'Blocked' for j in delivery_plan(cfg, '000001', d))


def test_360_auxiliaries_not_worker_inputs(integrated):
    _, cfg, _, _, _ = integrated
    root = cfg.inbox_dir / '000001/delivery/CAMERA360'
    root.mkdir()
    for ext in ('insv', 'lrv'): (root / ('camera.' + ext)).write_bytes(b'auxiliary fixture')
    declaration = close_fixture(template(cfg, '000001'))
    jobs = delivery_plan(cfg, '000001', declaration)
    assert len(jobs) == 1 and jobs[0]['status'] == 'Authorized'
    assert set(jobs[0]['sources']) == {'mom', 'child'}
    assert all(r['path'].endswith('.avi') for r in jobs[0]['sources'].values())


def test_corrupted_retained_output_blocks_reencoding(integrated):
    def disconnect(point):
        if point == 'before_commit': raise OSError('simulated disconnect')
    with pytest.raises(OSError, match='simulated disconnect'): execute(integrated, checkpoint=disconnect)
    (integrated[4][0] / 'outputs/mom.mp4').write_bytes(b'corrupt')
    with pytest.raises(Conflict, match='retained'): execute(integrated)
    assert len(integrated[4]) == 1
