"""Separate execution journal and crash recovery for the synthetic sandbox."""
import json
import os
import uuid

from .synthetic_plan import plan, contained
from .synthetic_local import process
from .synthetic_publish import exclusive, inspect, publish
from .fs_errors import check_path


def save(box, fingerprint, state):
    if len(fingerprint) != 64 or any(c not in '0123456789abcdef' for c in fingerprint):
        raise ValueError('invalid fingerprint')
    path = box.path('state', fingerprint + '.json')
    tmp = box.path('state', uuid.uuid4().hex + '.tmp')
    check_path(path)
    check_path(tmp)
    with open(tmp, 'x', encoding='utf-8') as handle:
        json.dump(state, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def run(box, cfg, participant, fingerprint, approvals, *, timeout=120,
        after_publish=lambda: None, before_rename=lambda: None):
    """Replan under a global sandbox lock. Retry by recalling with the same approval.

    No automatic retry of conflicts or scientific uncertainty. At most 3 attempts
    per fingerprint; a verified publication always allows journal recovery.
    """
    if cfg.followup_root.absolute() != box.path('input'):
        raise ValueError('configuration outside synthetic sandbox')
    for name in (cfg.inbox, cfg.raw, cfg.synced, cfg.logs_qc):
        contained(box.path('input'), cfg._dir(name))
    with exclusive(box.path('state', 'execution.lock')):
        jobs = plan(cfg, participant, approvals)
        job = next((j for j in jobs if j['fingerprint'] == fingerprint), None)
        if job is None or job['status'] != 'Authorized':
            raise ValueError('authorization invalid, blocked or stale')
        path = box.path('state', fingerprint + '.json')
        state = json.loads(path.read_text()) if path.exists() else dict(
            schema='synthetic-execution-1', fingerprint=fingerprint, attempts=0,
            processing_status='Planned', qc_status='NotApproved', history=[])
        def record(status, detail=''):
            state['processing_status'] = status
            state['history'] = (state['history'] + [dict(status=status, detail=detail)])[-30:]
            save(box, fingerprint, state)
        try:
            existing = inspect(box, job)
            if existing:
                record('Published', 'verified existing publication; no encoding')
                return existing
            if state['attempts'] >= 3:
                raise ValueError('retry limit exceeded')
            state['attempts'] += 1
            record('Running')
            outputs = process(box, cfg, job, timeout=timeout)
            record('TechnicallyValidated')
            final = publish(box, job, outputs, before_rename=before_rename)
            after_publish()
            record('Published')
            return final
        except Exception as exc:
            record('Failed', type(exc).__name__ + ': ' + str(exc))
            raise
