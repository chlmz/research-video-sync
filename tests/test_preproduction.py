import json

import pytest

from rg2019 import preproduction as pp
from rg2019.config import from_dict
from rg2019.delivery import template, delivery_plan
from rg2019.storage import Conflict, OUTPUTS
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
    with pytest.raises(OSError): execute(integrated, checkpoint=disconnect)
    assert execute(integrated).exists()
    assert len(integrated[4]) == 1


def test_retry_budget(integrated):
    def fail(point): raise OSError('simulated transient failure')
    for _ in range(3):
        with pytest.raises(OSError): execute(integrated, checkpoint=fail)
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
    with pytest.raises(pp.Blocked, match='changed'):
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
