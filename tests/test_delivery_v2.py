import copy
import json
import uuid
from pathlib import Path
import pytest
from rg2019 import delivery_v2 as v2
from rg2019.config import from_dict

SID = str(uuid.UUID(int=1))


@pytest.fixture
def selected(tmp_path):
    root = tmp_path / '00_INBOX/000001/session'
    root.mkdir(parents=True)
    for name in ('CAM-A/DCIM/mother.avi', 'CAM-B/DCIM/children.avi', '360/x.insv', '360/x.lrv'):
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'synthetic selection')
    return root


def generate(root, **kw):
    return v2.generate(root, participant='000001', session_id=SID,
                       closed_at='2026-01-01T00:00:00+00:00', selection_closed=True, **kw)


def verify(root, doc):
    return v2.verify(root, doc, participant='000001', session_id=SID)


def test_roundtrip_idempotence_originals_and_auxiliaries(selected, tmp_path):
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in selected.rglob('*') if p.is_file()}
    doc = generate(selected)
    assert doc == generate(selected)
    assert [r['material'] for r in doc['files']].count('Auxiliary360') == 2
    dest = tmp_path / 'receipt.json'
    v2.save(selected, dest, doc)
    mtime = dest.stat().st_mtime_ns
    v2.save(selected, dest, doc)
    assert dest.stat().st_mtime_ns == mtime
    assert verify(selected, doc)['status'] == 'ReceptionVerified'
    assert verify(selected, doc)['processing_authorized'] is False
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == r for p, r in before.items())


@pytest.mark.parametrize('case,status', [('all_missing','WaitingForDelivery'), ('missing','WaitingForDelivery'),
    ('changed','IntegrityError'), ('additional','NeedsReview')])
def test_receiver_arrival_order(selected, case, status):
    doc = generate(selected)
    if case in ('missing','all_missing'):
        targets = list(selected.rglob('*.avi')) if case == 'missing' else [p for p in selected.rglob('*') if p.is_file()]
        for p in targets: p.unlink()
    elif case == 'changed': next(selected.rglob('*.avi')).write_bytes(b'changed')
    else: (selected / 'extra.avi').write_bytes(b'extra')
    assert verify(selected, doc)['status'] == status


@pytest.mark.parametrize('field,value', [('schema','rg2019.delivery.v1'), ('participant',1), ('session_id','000001'),
    ('closed_at','2026-01-01'), ('selection_closed',False), ('delivery_id','wrong')])
def test_bad_contract_rejected(selected, field, value):
    doc = generate(selected)
    doc[field] = value
    assert verify(selected, doc)['status'] == 'NeedsReview'


def test_exclusions_and_rename_evidence(selected):
    doc = generate(selected, exclusions={'360/x.lrv':'preview not used scientifically'},
                   originals={'CAM-A/DCIM/mother.avi':'before/SNAP9.avi'})
    assert verify(selected, doc)['status'] == 'ReceptionVerified'
    record = next(r for r in doc['files'] if r['role'] == 'mom')
    assert record['game'] is None and record['original_name'] == 'before/SNAP9.avi'
    # An explicitly excluded file need not be transported to the receiver.
    (selected / '360/x.lrv').unlink()
    assert verify(selected, doc)['status'] == 'ReceptionVerified'


def test_manifest_self_inclusion_and_overwrite_blocked(selected, tmp_path):
    doc = generate(selected)
    with pytest.raises(ValueError, match='outside'): v2.save(selected, selected / 'manifest.json', doc)
    dest = tmp_path / 'existing.json'
    dest.write_text('{}')
    with pytest.raises(ValueError, match='conflict'): v2.save(selected, dest, doc)
    assert dest.read_text() == '{}'


def test_path_collision_and_traversal(selected):
    doc = generate(selected)
    for path in ('../escape.avi', doc['files'][1]['path'].upper()):
        bad = copy.deepcopy(doc)
        bad['files'][0]['path'] = path
        assert verify(selected, bad)['status'] == 'NeedsReview'


def test_changed_during_hashing(selected, monkeypatch):
    original = Path.open
    changed = False
    def mutate(path, *a, **k):
        nonlocal changed
        if not changed and a and a[0] == 'rb':
            changed = True
            with original(path, 'ab') as h: h.write(b'changed')
        return original(path, *a, **k)
    monkeypatch.setattr(Path, 'open', mutate)
    with pytest.raises(ValueError): generate(selected)


def test_incomplete_and_inaccessible(selected, monkeypatch):
    p = selected / 'copy.partial'
    p.write_bytes(b'pending')
    with pytest.raises(ValueError): generate(selected)
    p.unlink()
    monkeypatch.setattr(Path, 'open', lambda *a, **k: (_ for _ in ()).throw(PermissionError('synthetic ACL')))
    with pytest.raises(PermissionError): generate(selected)


def test_cli_roundtrip(selected, tmp_path, capsys):
    manifest = tmp_path / 'delivery.json'
    args = ['--root',str(selected),'--manifest',str(manifest),'--participant','000001','--session-id',SID]
    assert v2.main(['generate',*args,'--closed-at','2026-01-01T00:00:00+00:00','--closed']) == 0
    assert v2.main(['verify',*args]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])['qc_status'] == 'NotApproved'


def test_receipt_does_not_authorize_processing(selected):
    cfg = from_dict(dict(followup_root=str(selected.parents[2]), field_sessions={'000001':['session']}))
    doc = generate(selected)
    result = v2.reception_plan(cfg,'000001','session',doc,session_id=SID,session_reviewed=True)
    assert result['receipt']['status'] == 'ReceptionVerified'
    assert result['jobs'][0]['game_origin'] == 'inferred_unique_pair'
    assert result['jobs'][0]['status'] == 'Blocked'


def test_deep_unicode_paths_and_recovery(selected, tmp_path):
    p = selected
    for i in range(8): p = p / ('câmera' + str(i))
    p.mkdir(parents=True)
    (p / 'fixture.insv').write_bytes(b'auxiliary')
    doc = generate(selected)
    dest = tmp_path / 'torn.json'
    dest.write_text('{')
    with pytest.raises(ValueError): v2.save(selected,dest,doc)
    assert dest.read_text() == '{'
    assert verify(selected,doc)['status'] == 'ReceptionVerified'


def test_delivery_directory_not_arrived(selected, tmp_path):
    assert verify(tmp_path / 'not-arrived', generate(selected))['status'] == 'WaitingForDelivery'


def test_numbered_games_match_only_numbers(selected):
    for p in selected.rglob('*.avi'): p.rename(p.with_name(p.stem + '1.avi'))
    for role in ('mother','children'): (selected / (role + '2.avi')).write_bytes(b'game two')
    cfg = from_dict(dict(followup_root=str(selected.parents[2]), field_sessions={'000001':['session']}))
    result = v2.reception_plan(cfg,'000001','session',generate(selected),session_id=SID,session_reviewed=True)
    assert [j['game'] for j in result['jobs']] == [1,2]
    assert all(j['game_origin'] == 'explicit' for j in result['jobs'])


def test_receiver_identity_binds_uuid_even_when_directory_reused(selected):
    cfg = from_dict(dict(followup_root=str(selected.parents[2]), field_sessions={'000001':['session']}))
    doc = generate(selected)
    first = v2.reception_plan(cfg,'000001','session',doc,session_id=SID,session_reviewed=True)
    other = copy.deepcopy(doc)
    other['session_id'] = str(uuid.UUID(int=2))
    other['delivery_id'] = v2.identity(other)
    second = v2.reception_plan(cfg,'000001','session',other,session_id=other['session_id'],session_reviewed=True)
    assert first['jobs'][0]['fingerprint'] != second['jobs'][0]['fingerprint']
