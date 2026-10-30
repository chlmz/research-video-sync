"""Deterministic plans and explicit fixture-only approvals. No processing here."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .discovery import discover_field
from .media import sha256_file


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def contained(root, path):
    root, path = Path(root).absolute(), Path(path).absolute()
    if not path.is_relative_to(root):
        raise ValueError('path outside synthetic workspace')
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ValueError('links are forbidden in synthetic workspace')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('path escapes workspace')
    return path


def plan(cfg, participant, approvals=None):
    """Hash sources; approval binds the exact inventory and scientific parameters.

    Approvals are explicit synthetic test contracts, not clinical authorization.
    Empty/unresolved discoveries produce a blocked placeholder job.
    """
    report = discover_field(cfg, participant)
    approvals = approvals or {}
    inventory = digest(report)
    files = {f['relative_path']: f for f in report['files']}
    jobs = []
    sessions = report['sessions'] or [{'session_id': None, 'games': []}]
    for session in sessions:
        for game in session['games'] or [{'game': None, 'status': 'NeedsReview', 'sources': []}]:
            reasons = []
            if report['issues']:
                reasons.append('DiscoveryIssues')
            if not session['session_id'] or game['status'] != 'CandidatePair':
                reasons.append('AmbiguousPair')
            sources = {}
            for rel in game['sources']:
                f = files[rel]
                try:
                    p = contained(cfg.inbox_dir / participant, cfg.inbox_dir / participant / rel)
                    before = p.stat()
                    sha = sha256_file(p)
                    after = p.stat()
                    if (before.st_size, before.st_mtime_ns) != (f['size'], f['mtime_ns']) or (
                            before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise ValueError('input changed during hashing')
                    sources[f['role']] = dict(path=rel, sha256=sha, size=before.st_size,
                                               evidence=f['evidence'])
                except (OSError, ValueError) as exc:
                    reasons.append('InputReadError:' + str(exc))
            identity = dict(participant=participant, session=session['session_id'], game=game['game'],
                            sources=sources, inventory=inventory,
                            sync=asdict(cfg.sync), encode=asdict(cfg.encode))
            fingerprint = digest(identity)
            approval = approvals.get(fingerprint, {})
            for gate in ('synthetic_only', 'session_reviewed', 'delivery_complete', 'integrity_verified'):
                if approval.get(gate) is not True:
                    reasons.append(gate)
            if approval.get('fingerprint') != fingerprint or not approval.get('evidence'):
                reasons.append('ApprovalEvidenceMissing')
            jobs.append(dict(**identity, fingerprint=fingerprint,
                             status='Blocked' if reasons else 'Authorized', reasons=sorted(set(reasons)),
                             qc_status='NotApproved'))
    return jobs
