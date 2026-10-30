"""Create a NEW local fixture sandbox; demonstrate publication crash recovery."""
import argparse
import json
from pathlib import Path
import runpy
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from rg2019.config import from_dict
from rg2019.synthetic_local import Sandbox
from rg2019.synthetic_plan import plan
from rg2019.synthetic_run import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='new empty local path, never a scientific tree')
    args = parser.parse_args()
    box = Sandbox.create(args.root)
    helpers = runpy.run_path(str(REPO / 'tests' / 'helpers.py'))
    cfg = from_dict(dict(followup_root=str(box.path('input')), field_sessions={'000001': ['delivery']},
                        sync=dict(max_lag_seconds=5, window_seconds=4, fine_search_seconds=1),
                        encode=dict(preset='ultrafast', crf=30)))
    signal = helpers['wall_signal'](45, 16000, seed=729)
    for role, start in [('mother', 0), ('children', 2)]:
        path = box.path('input', '00_INBOX', '000001', 'delivery', role + '1.avi')
        helpers['make_video'](path, helpers['recording'](signal, 16000, start, 40), 16000, 40)
    blocked = plan(cfg, '000001')[0]
    fp = blocked['fingerprint']
    approval = {fp: dict(fingerprint=fp, synthetic_only=True, session_reviewed=True,
                        delivery_complete=True, integrity_verified=True, evidence='generated fixture seed 729')}
    def interrupt():
        raise RuntimeError('intentional demonstration: publication done, journal not saved')
    try:
        run(box, cfg, '000001', fp, approval, after_publish=interrupt)
    except RuntimeError as exc:
        if str(exc) != 'intentional demonstration: publication done, journal not saved':
            raise
    final = run(box, cfg, '000001', fp, approval)
    assert run(box, cfg, '000001', fp, approval) == final
    state = json.loads(box.path('state', fp + '.json').read_text())
    assert state['attempts'] == 1 and state['qc_status'] == 'NotApproved'
    print(json.dumps(dict(publication=str(final), recovered=True, attempts=state['attempts'],
                          qc_status=state['qc_status']), indent=2))


if __name__ == '__main__':
    main()
