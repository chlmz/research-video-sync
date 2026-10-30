"""Three invented field layouts, generated media, conservative gates and recovery."""
import argparse
import json
from pathlib import Path
import runpy
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from rg2019.config import from_dict
from rg2019.delivery import template, delivery_plan
from rg2019.media import sha256_file
from rg2019.preproduction import initialize, Settings, run


def demonstrate(root):
    root = initialize(root)
    helpers = runpy.run_path(str(REPO / 'tests/helpers.py'))
    signal = helpers['wall_signal'](45, 16000, seed=731)
    generated = {}
    for role, start in [('mother', 0), ('children', 2)]:
        path = root / 'scratch' / (role + '.avi')
        helpers['make_video'](path, helpers['recording'](signal, 16000, start, 40), 16000, 40)
        generated[role] = path
    patterns = {
        '000001': [('delivery/date-X/CAM-A/DCIM/a/b/Mother.avi', 'mother'),
                   ('delivery/date-X/CAM-B/DCIM/c/d/Children.avi', 'children')],
        '000002': [('delivery/repeated/repeated/CAM-A/mother.avi', 'mother'),
                   ('delivery/CAM-B/children.avi', 'children')],
        '000003': [(f'delivery-A/CAM-{r}/{r}{g}.avi', r)
                   for g in (1, 2) for r in ('mother', 'children')] +
                  [(f'delivery-B/CAM-{r}/{r}1.avi', r) for r in ('mother', 'children')],
    }
    for pid, paths in patterns.items():
        for rel, role in paths:
            path = root / '00_INBOX' / pid / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(generated[role], path)
    cfg = from_dict(dict(followup_root=str(root), field_sessions={
        '000001': ['delivery'], '000002': ['delivery'], '000003': ['delivery-A', 'delivery-B']},
        sync=dict(max_lag_seconds=5, window_seconds=4, fine_search_seconds=1),
        encode=dict(preset='ultrafast', crf=30)))
    # This explicit closure is only for fixtures generated above, never field data.
    declarations = {}
    for pid in patterns:
        declaration = template(cfg, pid)
        for session in declaration['sessions'].values():
            session.update(closed=True, session_reviewed=True, reviewer='synthetic-generator',
                           evidence='generated known inventory seed 731; not scientific approval',
                           closed_at='2026-01-01T00:00:00+00:00')
        declarations[pid] = declaration
        (root / (pid + '-declaration.json')).write_text(json.dumps(declaration, indent=2), encoding='utf-8')
    before = {p: (sha256_file(p), p.stat().st_mtime_ns) for p in (root / '00_INBOX').rglob('*.avi')}
    settings = Settings(str(root), enabled=True)
    blocked, publications = [], []
    interrupted = False
    def crash_once(point):
        nonlocal interrupted
        if point == 'after_commit' and not interrupted:
            interrupted = True
            raise KeyboardInterrupt('synthetic crash after commit acknowledgement')
    for pid, declaration in declarations.items():
        jobs = delivery_plan(cfg, pid, declaration)
        for job in jobs:
            if job['status'] == 'Blocked':
                blocked.append(dict(participant=pid, game=job['game'], reasons=job['reasons']))
                continue
            try:
                run(settings, cfg, pid, job['fingerprint'], declaration, checkpoint=crash_once)
            except KeyboardInterrupt as exc:
                if str(exc) != 'synthetic crash after commit acknowledgement':
                    raise
            final = run(settings, cfg, pid, job['fingerprint'], declaration)
            assert run(settings, cfg, pid, job['fingerprint'], declaration) == final
            evidence = json.loads((final / 'sync.json').read_text(encoding='utf-8'))
            assert abs(evidence['offset_seconds'] - 2) < 0.15
            state = json.loads((root / 'state' / (job['fingerprint'] + '.json')).read_text(encoding='utf-8'))
            assert state['attempts'] == 1 and state['qc_status'] == 'NotApproved'
            publications.append(str(final))
    assert all((sha256_file(p), p.stat().st_mtime_ns) == record for p, record in before.items())
    assert len(blocked) == 2 and len(publications) == 3 and interrupted
    return dict(blocked=blocked, publications=publications, recovered=True,
                originals_unchanged=True, qc_status='NotApproved', real_smb_validated=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path, help='NEW local synthetic directory')
    print(json.dumps(demonstrate(parser.parse_args().root), indent=2))
