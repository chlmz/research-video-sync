import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from rg2019.config import from_dict, ConfigError
from rg2019.discovery import discover_field
from rg2019.state import migrate_field_state, new_state


def setup(tmp_path, files, sessions=('delivery',), pid='001234'):
    cfg = from_dict(dict(followup_root=str(tmp_path), field_sessions={pid: list(sessions)}))
    root = cfg.inbox_dir / pid
    root.mkdir(parents=True)
    for name in files:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'synthetic inventory fixture')
    return cfg, root


def test_three_field_patterns(tmp_path):
    patterns = [
        ['delivery/20261001/CAM1/a/b/c/Mother.avi', 'delivery/20261001/CAM2/d/e/f/Children.avi'],
        ['delivery/repeated/repeated/CAM1/mother.avi', 'delivery/CAM2/children.avi'],
        ['delivery/CAM1/mother1.avi', 'delivery/CAM2/children1.avi',
         'delivery/CAM1/mother2.avi', 'delivery/CAM2/children2.avi'],
    ]
    for i, files in enumerate(patterns):
        cfg, root = setup(tmp_path / str(i), files, pid=f'{i:06d}')
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
        report = discover_field(cfg, root.name)
        games = report['sessions'][0]['games']
        assert [g['status'] for g in games] == (['NeedsReview'] if i < 2 else ['CandidatePair'] * 2)
        if i < 2:
            assert games[0]['game'] is None
            assert games[0]['review_code'] == 'REVIEW_GAME_UNSPECIFIED'
        assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before
        assert report['delivery_status'] == 'WaitingForDelivery'
        assert report['integrity_status'] == 'NotVerified'
        assert report['qc_status'] == 'NotApproved'


@pytest.mark.parametrize('name,code', [
    ('mother_child1.avi', 'REVIEW_ROLE_CONTRADICTORY'),
    ('mohter1.avi', 'REVIEW_ROLE_UNKNOWN'),
    ('mother_20261001_cam2_001.avi', 'REVIEW_GAME_UNSPECIFIED'),
    ('mother20261001.avi', 'REVIEW_GAME_CONTRADICTORY'),
    ('mother0.avi', 'REVIEW_GAME_CONTRADICTORY'),
    ('mother1_children2.avi', 'REVIEW_GAME_CONTRADICTORY'),
])
def test_classification_evidence(tmp_path, name, code):
    cfg, _ = setup(tmp_path, ['delivery/' + name])
    report = discover_field(cfg, '001234')
    assert code in report['files'][0]['review_codes']
    assert all(g['status'] == 'NeedsReview' for g in report['sessions'][0]['games'])


def test_never_cross_sessions(tmp_path):
    cfg, _ = setup(tmp_path, ['a/mother1.avi', 'b/children1.avi'], sessions=('a', 'b'))
    r = discover_field(cfg, '001234')
    assert len(r['sessions']) == 2
    assert all(s['games'][0]['status'] == 'NeedsReview' for s in r['sessions'])


def test_unknown_session_no_pair(tmp_path):
    cfg, _ = setup(tmp_path, ['a/mother1.avi', 'b/children1.avi'], sessions=())
    r = discover_field(cfg, '001234')
    assert not r['sessions']
    assert all('REVIEW_SESSION_UNSPECIFIED' in f['review_codes'] for f in r['files'])


def test_auto_sessions_only_for_complete_top_level_partitions(tmp_path):
    cfg, _ = setup(tmp_path, ['delivery_a/CAM1/mother1.avi', 'delivery_a/CAM2/children1.avi',
                             'delivery_b/CAM1/mother1.avi', 'delivery_b/CAM2/children1.avi'], sessions=())
    report = discover_field(cfg, '001234')
    assert [s['session_id'] for s in report['sessions']] == ['delivery_a', 'delivery_b']
    assert all(s['session_origin'] == 'inferred_top_level' for s in report['sessions'])
    assert all(s['games'][0]['status'] == 'CandidatePair' for s in report['sessions'])
    assert not any(i['code'] == 'REVIEW_DUPLICATE_NAME' for i in report['issues'])
    assert report['delivery_status'] == 'WaitingForDelivery'


def test_auto_sessions_reject_incomplete_or_mixed_partitions(tmp_path):
    cfg, _ = setup(tmp_path, ['delivery_a/mother1.avi', 'delivery_a/children1.avi',
                             'delivery_b/mother1.avi'], sessions=())
    report = discover_field(cfg, '001234')
    assert not report['sessions']
    assert all(f['session'] is None for f in report['files'])


def test_auto_sessions_reject_loose_avi(tmp_path):
    cfg, _ = setup(tmp_path, ['delivery_a/mother1.avi', 'delivery_a/children1.avi',
                             'mother2.avi'], sessions=())
    report = discover_field(cfg, '001234')
    assert not report['sessions']


def test_same_names_in_independent_explicit_sessions_are_legitimate(tmp_path):
    cfg, _ = setup(tmp_path, ['a/mother1.avi', 'a/children1.avi',
                             'b/mother1.avi', 'b/children1.avi'], sessions=('a', 'b'))
    report = discover_field(cfg, '001234')
    assert all(s['games'][0]['status'] == 'CandidatePair' for s in report['sessions'])
    assert all(s['session_origin'] == 'configured' for s in report['sessions'])
    assert not any(i['code'] == 'REVIEW_DUPLICATE_NAME' for i in report['issues'])


def test_duplicate_name_inside_auto_session_is_conflict(tmp_path):
    cfg, _ = setup(tmp_path, ['delivery/CAM1/mother1.avi', 'delivery/CAM2/children1.avi',
                             'delivery/backup/mother1.avi'], sessions=())
    report = discover_field(cfg, '001234')
    assert report['sessions'][0]['games'][0]['status'] == 'NeedsReview'
    assert sum(i['code'] == 'REVIEW_DUPLICATE_NAME' for i in report['issues']) == 2


def test_auto_sessions_do_not_use_camera_directories_as_sessions(tmp_path):
    cfg, _ = setup(tmp_path, ['CAM1/mother1.avi', 'CAM2/children1.avi'], sessions=())
    report = discover_field(cfg, '001234')
    assert not report['sessions']
    assert all('REVIEW_SESSION_UNSPECIFIED' in f['review_codes'] for f in report['files'])


@pytest.mark.parametrize('extra', ['copy/mother1.avi', 'copy/MOTHER1.AVI', 'other_mom1.avi', 'mohter1.avi'])
def test_duplicate_or_extra_candidate_blocks_pair(tmp_path, extra):
    cfg, _ = setup(tmp_path, ['delivery/mother1.avi', 'delivery/children1.avi', 'delivery/' + extra])
    r = discover_field(cfg, '001234')
    assert all(g['status'] == 'NeedsReview' for g in r['sessions'][0]['games'])


def test_auxiliary_and_manifest(tmp_path):
    cfg, root = setup(tmp_path, ['delivery/mother1.avi', 'delivery/children1.avi',
                               'delivery/CAMERA360/mother1.insv', 'delivery/CAMERA360/children1.lrv',
                               'delivery/copy.json', 'delivery/unknown.json'])
    (root / 'delivery/copy.json').write_text(json.dumps(dict(schema='rg2019.inventory.v1',
        files=[dict(relative_path='missing.avi', size=99)])))
    r = discover_field(cfg, '001234')
    assert len(r['sessions'][0]['games'][0]['sources']) == 2
    assert r['sessions'][0]['manifest_status'] == 'ManifestMismatch'
    assert {'MANIFEST_MISMATCH', 'REVIEW_MANIFEST_SCHEMA'} <= {i['code'] for i in r['issues']}
    assert r['sessions'][0]['integrity_status'] == 'NotVerified'


def test_links_not_followed(tmp_path):
    cfg, root = setup(tmp_path, ['delivery/mother1.avi'])
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'children1.avi').write_bytes(b'outside')
    (root / 'delivery/link').symlink_to(outside, target_is_directory=True)
    (root / 'delivery/children1.avi').symlink_to(outside / 'children1.avi')
    r = discover_field(cfg, '001234')
    assert len(r['files']) == 1
    assert sum(i['code'] == 'LINK_EXCLUDED' for i in r['issues']) == 2


@pytest.mark.parametrize('roots', [['../escape'], ['/absolute'], ['a', 'a/b'], ['.', 'a'], ['a', 'a'], ['C:\\data']])
def test_invalid_session_config(tmp_path, roots):
    with pytest.raises(ConfigError):
        from_dict(dict(followup_root=str(tmp_path), field_sessions={'001234': roots}))


def test_migration_lossless_and_idempotent():
    old = new_state('ID100392', 'now')
    old['status'] = 'SUCCESS'
    old['sources'] = {'mom': {'name': 'original.avi', 'sha256': 'abc'}}
    original = copy.deepcopy(old)
    migrated = migrate_field_state(old)
    assert old == original == migrated['legacy_state']
    assert migrate_field_state(migrated) == migrated
    assert migrated['sessions'][0]['games'][0]['game'] is None
    assert migrated['qc_status'] == 'NotApproved'


def test_cli_only_outputs_json(tmp_path):
    cfg, root = setup(tmp_path, ['delivery/mother1.avi', 'delivery/children1.avi'])
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(dict(followup_root=str(tmp_path), field_sessions=cfg.field_sessions)))
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob('*'))
    run = subprocess.run([sys.executable, str(Path(__file__).parents[1] / 'discover_rg2019.py'),
                          '--config', str(config), '--participant', '001234'], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)['sessions'][0]['games'][0]['status'] == 'CandidatePair'
    assert before == sorted(p.relative_to(root).as_posix() for p in root.rglob('*'))


def test_valid_separate_sessions_and_directory_roles(tmp_path):
    cfg, _ = setup(tmp_path, ['a/mother1/cam7_20261001_001.avi',
                             'a/children1/cam8_20261001_001.avi',
                             'b/B_mom2.avi', 'b/B_child2.avi'], sessions=('a', 'b'))
    r = discover_field(cfg, '001234')
    assert [s['games'][0]['game'] for s in r['sessions']] == [1, 2]
    assert all(s['games'][0]['status'] == 'CandidatePair' for s in r['sessions'])
    assert r['files'][0]['evidence']


def test_transfer_files_never_candidates(tmp_path):
    cfg, _ = setup(tmp_path, ['delivery/.syno_mother1.avi', 'delivery/children1.avi'])
    r = discover_field(cfg, '001234')
    assert r['files'][0]['kind'] == 'TransferInProgress'
    assert r['sessions'][0]['games'][0]['status'] == 'NeedsReview'
    assert any(i['code'] == 'TRANSFER_IN_PROGRESS' for i in r['issues'])


def test_matching_manifest_is_not_integrity_or_completeness(tmp_path):
    cfg, root = setup(tmp_path, ['delivery/mother1.avi', 'delivery/children1.avi'])
    (root / 'delivery/log.json').write_text(json.dumps(dict(schema='rg2019.inventory.v1',
        files=[dict(relative_path=p.name, size=p.stat().st_size) for p in (root / 'delivery').glob('*.avi')])) )
    r = discover_field(cfg, '001234')
    session = r['sessions'][0]
    assert session['manifest_status'] == 'InventoryMatches'
    assert session['integrity_status'] == 'NotVerified'
    assert session['delivery_status'] == 'WaitingForDelivery'
    assert session['qc_status'] == 'NotApproved'


def test_unreadable_branch_is_reported(tmp_path, monkeypatch):
    cfg, root = setup(tmp_path, ['delivery/blocked/mother1.avi'])
    original = Path.iterdir
    def guarded(path):
        if path.name == 'blocked':
            raise PermissionError('synthetic denial')
        return original(path)
    monkeypatch.setattr(Path, 'iterdir', guarded)
    r = discover_field(cfg, '001234')
    assert any(i['code'] == 'SCAN_ERROR' for i in r['issues'])
    assert r['delivery_status'] == 'WaitingForDelivery'
