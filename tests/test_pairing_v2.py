import pytest
from rg2019.discovery import discover_field
from rg2019.synthetic_plan import plan
from test_field_discovery import setup


def test_unique_pair_requires_explicit_review(tmp_path):
    cfg, _ = setup(tmp_path, ['delivery/mother.avi', 'delivery/children.avi'])
    assert discover_field(cfg, '001234')['sessions'][0]['games'][0]['game'] is None
    job = plan(cfg, '001234', reviewed_sessions=['delivery'])[0]
    assert job['game'] == 1 and job['game_origin'] == 'inferred_unique_pair'
    assert job['status'] == 'Blocked' and job['qc_status'] == 'NotApproved'


@pytest.mark.parametrize('extra', ['mother2.avi', 'copy/mother.avi', 'mohter.avi', 'mother_child.avi'])
def test_extra_candidates_prevent_inference(tmp_path, extra):
    cfg, _ = setup(tmp_path, ['delivery/mother.avi', 'delivery/children.avi', 'delivery/' + extra])
    report = discover_field(cfg, '001234', reviewed_sessions=['delivery'])
    assert not any(f.get('game_origin') == 'inferred_unique_pair' for f in report['files'])


def test_two_reviewed_sessions_do_not_cross(tmp_path):
    cfg, _ = setup(tmp_path, [s + '/' + r + '.avi' for s in ('a','b') for r in ('mother','children')], sessions=('a','b'))
    jobs = plan(cfg, '001234', reviewed_sessions=['a','b'])
    assert len(jobs) == 2 and {j['session'] for j in jobs} == {'a','b'}
    assert all(j['game'] == 1 for j in jobs)
