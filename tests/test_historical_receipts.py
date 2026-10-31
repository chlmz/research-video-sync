import copy
from rg2019.historical_receipts import reconcile


def test_thirteen_records_eight_avis_no_identity_inferred():
    records = [dict(path=f'old/CAM-A/SNAP{i}.avi', size=100, session_id='000001',
                    camera_id='CAM-A', snap=i) for i in range(13)]
    before = copy.deepcopy(records)
    observed = {f'new/CAM-{i % 2}/mother{i}.avi':100 for i in range(8)}
    report = reconcile(records, observed)
    assert report['historical_count'] == 13 and report['observed_count'] == 8
    assert all(len(r['size_candidates']) == 8 and not r['identity_demonstrated'] for r in report['records'])
    assert not report['delivery_complete'] and not report['session_identity_verified']
    assert records == before and len(observed) == 8


def test_matching_name_size_still_not_proven():
    report = reconcile([dict(path='mother1.avi', size=3, snap=9, camera_id='child-camera')], {'mother1.avi':3})
    row = report['records'][0]
    assert row['current_path_present'] and not row['identity_demonstrated']
    assert 'game' not in row and 'role' not in row
    assert report['qc_status'] == 'NotApproved'
