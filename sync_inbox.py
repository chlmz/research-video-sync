#!/usr/bin/env python3
"""Discover complete two- or three-camera TeenCam sets; preview by default."""
import argparse
import re
import subprocess
import sys
from pathlib import Path

from rg2019 import config

ROLES = {'mom': ('parent view point', 'mum view point', 'mom view point'),
         'child': ('teen view point',), 'third': ('third camera',)}
VIDEO_SUFFIXES = {'.avi', '.mp4', '.mov', '.mkv', '.m4v'}
ID = re.compile(r'^(#?\d{2,8})(?!\d)', re.I)


def discover(inbox, mom_pattern=None, child_pattern=None, video_extensions=VIDEO_SUFFIXES):
    labels = {
        'mom': (*ROLES['mom'], mom_pattern),
        'child': (*ROLES['child'], child_pattern),
        'third': ROLES['third'],
    }
    extensions = {suffix.lower() if suffix.startswith('.') else f'.{suffix.lower()}'
                  for suffix in video_extensions}
    grouped = {}
    for path in sorted(inbox.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        match = ID.match(path.stem)
        if not match:
            print('IGNORED (no leading study ID):', path.name)
            continue
        pid = '#' + match.group(1).lstrip('#')
        stem = path.stem.casefold()
        hits = [role for role, names in labels.items()
                if any(name and name.casefold() in stem for name in names)]
        if len(hits) != 1:
            print('IGNORED (ambiguous camera label):', path.name)
            continue
        grouped.setdefault(pid, {}).setdefault(hits[0], []).append(path)
    return grouped


def complete_camera_sets(roles):
    """Return complete camera sets grouped by their common source folder."""
    by_folder = {}
    for role, files in roles.items():
        for path in files:
            by_folder.setdefault(path.parent, {}).setdefault(role, []).append(path)
    return [
        folder_roles
        for folder_roles in by_folder.values()
        if len(folder_roles.get('mom', [])) == 1
        and len(folder_roles.get('child', [])) == 1
        and len(folder_roles.get('third', [])) <= 1
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path, help='Folder containing 00_INBOX')
    parser.add_argument('--config', required=True, type=Path, help='Existing rg2019 config.json')
    parser.add_argument('--apply', action='store_true', help='Generate videos (default: preview only)')
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if not args.config.is_file(): parser.error('Missing config: ' + str(args.config))
    try:
        cfg = config.load(args.config)
    except config.ConfigError as exc:
        parser.error(str(exc))
    cfg.followup_root = root
    inbox = cfg.inbox_dir
    if not inbox.is_dir(): parser.error('Missing configured inbox folder: ' + str(inbox))
    groups = discover(inbox, cfg.mom_pattern, cfg.child_pattern, cfg.video_extensions)
    if not groups:
        print('No recognised videos in 00_INBOX.'); return 1
    ready, incomplete = [], []
    for pid, roles in sorted(groups.items()):
        camera_sets = complete_camera_sets(roles)
        if len(camera_sets) == 1:
            ready.append((pid, camera_sets[0]))
        else:
            details = ', '.join(f'{role}={len(roles.get(role, []))}' for role in ROLES)
            details += f'; complete folders={len(camera_sets)}'
            incomplete.append((pid, details))
    print(f'Found {len(groups)} participant IDs; {len(ready)} valid 2- or 3-camera sets; {len(incomplete)} incomplete/duplicate sets.')
    for pid, details in incomplete: print('SKIP:', pid, details)
    if not ready: return 1
    print('Mode:', 'APPLY' if args.apply else 'PREVIEW')
    for pid, roles in ready:
        print(f'  {pid}: {len(roles)} cameras')
    failed = []
    script = Path(__file__).with_name('sync_three_cameras_v2.py')
    for pid, roles in ready:
        print('\n' + '='*60 + '\nParticipant ' + pid, flush=True)
        command = [sys.executable, str(script), '--config', str(args.config), '--root', str(root), '--id', pid]
        if args.apply: command.append('--apply')
        result = subprocess.run(command, check=False)
        if result.returncode: failed.append(pid)
    print(f'\nCompleted attempts: {len(ready)-len(failed)}/{len(ready)}; failed: {len(failed)}')
    if failed: print('Failed IDs:', ', '.join(failed))
    print('Original recordings were not moved. Review video alignment manually.')
    return 1 if failed else 0

if __name__ == '__main__':
    sys.exit(main())
