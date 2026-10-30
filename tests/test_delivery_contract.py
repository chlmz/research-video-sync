"""Invented identifiers and byte fixtures, not scientific data."""
import copy

import pytest

from rg2019.config import from_dict
from rg2019.delivery import template, delivery_plan


@pytest.fixture
def delivery(tmp_path):
    cfg = from_dict(dict(followup_root=str(tmp_path), field_sessions={'000001': ['delivery']}))
    for name in ('mother1', 'children1'):
        p = cfg.inbox_dir / '000001' / 'delivery' / (name + '.avi')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'synthetic')
    return cfg


def close_fixture(d):
    d = copy.deepcopy(d)
    for s in d['sessions'].values():
        s.update(session_reviewed=True, closed=True, reviewer='synthetic-test',
                 evidence='invented closed delivery', closed_at='2026-01-01T00:00:00+00:00')
    return d


def test_template_cannot_authorize(delivery):
    job = delivery_plan(delivery, '000001', template(delivery, '000001'))[0]
    assert job['status'] == 'Blocked'
    assert job['delivery']['delivery_status'] == 'WaitingForDelivery'
    assert job['delivery']['integrity_status'] == 'IntegrityVerified'
    assert job['qc_status'] == 'NotApproved'


def test_closed_fixture_separates_all_states(delivery):
    declaration = close_fixture(template(delivery, '000001'))
    job = delivery_plan(delivery, '000001', declaration)[0]
    assert job['status'] == 'Authorized'
    assert job['delivery']['delivery_status'] == 'DeclaredComplete'
    assert job['technical_status'] == 'NotRun' and job['qc_status'] == 'NotApproved'


@pytest.mark.parametrize('fault', ['schema', 'inventory', 'closed', 'reviewer', 'timezone', 'games', 'hash', 'qc'])
def test_contract_mismatch_blocks(delivery, fault):
    d = close_fixture(template(delivery, '000001'))
    s = d['sessions']['delivery']
    if fault == 'schema': d['schema'] = 'unknown-field-log'
    elif fault == 'inventory': d['inventory'] = 'stale'
    elif fault == 'closed': s['closed'] = False
    elif fault == 'reviewer': s['reviewer'] = ''
    elif fault == 'timezone': s['closed_at'] = '2026-01-01'
    elif fault == 'games': s['expected_games'] = [1, 2]
    elif fault == 'hash': next(iter(s['files'].values()))['sha256'] = 'wrong'
    else: s['qc_approved'] = True
    assert delivery_plan(delivery, '000001', d)[0]['status'] == 'Blocked'


def test_changed_file_invalidates_delivery(delivery):
    d = close_fixture(template(delivery, '000001'))
    (delivery.inbox_dir / '000001/delivery/mother1.avi').write_bytes(b'changed')
    assert delivery_plan(delivery, '000001', d)[0]['status'] == 'Blocked'
