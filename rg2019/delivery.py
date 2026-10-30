"""Versioned delivery declarations, independent of processing and scientific QC.

Templates describe observations, never certify completeness. Field copy JSON is
still auxiliary evidence; accepting a new field schema requires an explicit adapter.
"""
from datetime import datetime

from .discovery import discover_field
from .media import sha256_file
from .synthetic_plan import contained, digest, plan

SCHEMA = 'rg2019.delivery.v1'


def snapshot(cfg, participant):
    report = discover_field(cfg, participant)
    records = {}
    for file in report['files']:
        path = contained(cfg.inbox_dir / participant,
                         cfg.inbox_dir / participant / file['relative_path'])
        before = path.stat()
        sha = sha256_file(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or (
                before.st_size, before.st_mtime_ns) != (file['size'], file['mtime_ns']):
            raise ValueError('delivery changed during inventory')
        records[file['relative_path']] = dict(size=after.st_size, sha256=sha)
    return report, records


def template(cfg, participant):
    """Unapproved draft for independent review, stored outside INBOX/RAW."""
    report, records = snapshot(cfg, participant)
    return dict(schema=SCHEMA, participant=participant, inventory=digest(report),
                sessions={s['session_id']: dict(
                    session_reviewed=False, closed=False, evidence='', reviewer='', closed_at='',
                    expected_games=[g['game'] for g in s['games']],
                    files={f['relative_path']: records[f['relative_path']]
                           for f in report['files'] if f['session'] == s['session_id']}
                ) for s in report['sessions']})


def delivery_plan(cfg, participant, declaration):
    """Conservatively adapt an explicit declaration to the existing planner.

    Every declared path/hash and the complete discovery inventory must match.
    Human declarations of closure/session boundaries are separate from computed
    integrity. No QC flag is accepted or promoted by this function.
    """
    report, records = snapshot(cfg, participant)
    drafts = plan(cfg, participant)
    valid_header = (isinstance(declaration, dict) and
                    set(declaration) == {'schema', 'participant', 'inventory', 'sessions'} and
                    declaration.get('schema') == SCHEMA and
                    declaration.get('participant') == participant and
                    declaration.get('inventory') == digest(report) and
                    isinstance(declaration.get('sessions'), dict) and
                    set(declaration['sessions']) == {s['session_id'] for s in report['sessions']})
    approvals, states = {}, {}
    for session in report['sessions']:
        sid = session['session_id']
        d = declaration['sessions'].get(sid, {}) if valid_header else {}
        keys = {'session_reviewed', 'closed', 'evidence', 'reviewer', 'closed_at', 'expected_games', 'files'}
        valid = isinstance(d, dict) and set(d) == keys
        observed = {f['relative_path']: records[f['relative_path']]
                    for f in report['files'] if f['session'] == sid}
        integrity = valid and bool(observed) and d['files'] == observed
        games = [g['game'] for g in session['games']]
        try:
            dated = valid and datetime.fromisoformat(d['closed_at']).utcoffset() is not None
        except (ValueError, TypeError):
            dated = False
        closed = (valid and d['closed'] is True and dated and
                  all(isinstance(d[k], str) and bool(d[k].strip()) for k in ('reviewer', 'evidence')) and
                  all(type(g) is int and g > 0 for g in games) and bool(games) and
                  isinstance(d['expected_games'], list) and
                  all(type(g) is int for g in d['expected_games']) and d['expected_games'] == games)
        reviewed = valid and d['session_reviewed'] is True
        states[sid] = dict(delivery_status='DeclaredComplete' if closed else 'WaitingForDelivery',
                           integrity_status='IntegrityVerified' if integrity else 'NotVerified',
                           session_status='Reviewed' if reviewed else 'NeedsReview',
                           manifest_status=session['manifest_status'])
        for job in drafts:
            if job['session'] == sid:
                fp = job['fingerprint']
                approvals[fp] = dict(fingerprint=fp, synthetic_only=True,
                    session_reviewed=reviewed, delivery_complete=bool(closed),
                    integrity_verified=bool(integrity), evidence=d.get('evidence', '') if valid else '')
    jobs = plan(cfg, participant, approvals)
    for job in jobs:
        job['delivery'] = states.get(job['session'], dict(delivery_status='WaitingForDelivery',
            integrity_status='NotVerified', session_status='NeedsReview', manifest_status='NotChecked'))
        job['declaration_digest'] = digest(declaration)
        job['technical_status'] = 'NotRun'
        # This planner is only an authorization to run synthetic preproduction.
        job['scope'] = 'synthetic-preproduction'
    return jobs
