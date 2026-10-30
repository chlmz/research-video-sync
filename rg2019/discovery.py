"""Participant-id validation and mother/child source discovery.

Discovery is deliberately strict: it never picks "the first match".  Zero or several
plausible candidates for either role are reported to the caller, which stops the
participant and flags it for manual review.
"""
from __future__ import annotations

import re
import os
import stat
import json
import difflib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config

# Names that are never participants / never sources (Synology, Windows, macOS artefacts).
IGNORED_DIR_PREFIXES = (".", "@", "#", "$")
IGNORED_FILE_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
# Files that indicate a transfer is still in progress (Synology Drive / browsers / editors).
TRANSIT_SUFFIXES = (".tmp", ".partial", ".part", ".crdownload", ".download", ".filepart")
TRANSIT_PREFIXES = (".~", "~$", ".syno")


def is_ignored_dir(name: str) -> bool:
    return name.startswith(IGNORED_DIR_PREFIXES)


def is_transit_file(name: str) -> bool:
    low = name.lower()
    return low.endswith(TRANSIT_SUFFIXES) or low.startswith(TRANSIT_PREFIXES)


def is_junk_file(name: str) -> bool:
    return name.lower() in IGNORED_FILE_NAMES


def valid_participant_id(cfg: Config, name: str) -> bool:
    return re.fullmatch(cfg.participant_id_regex, name) is not None


@dataclass
class Discovery:
    mom: list[Path] = field(default_factory=list)
    child: list[Path] = field(default_factory=list)
    both: list[Path] = field(default_factory=list)   # match BOTH patterns -> ambiguous

    @property
    def problem(self) -> str | None:
        """None if exactly one mom and one child; otherwise 'MISSING' or 'AMBIGUOUS'."""
        if self.both or len(self.mom) > 1 or len(self.child) > 1:
            return "AMBIGUOUS"
        if not self.mom or not self.child:
            return "MISSING"
        return None

    def describe(self) -> str:
        def names(xs):
            return ", ".join(p.name for p in xs) or "none"
        return (f"mom candidates: [{names(self.mom)}]; child candidates: [{names(self.child)}]"
                + (f"; matching both patterns: [{names(self.both)}]" if self.both else ""))


def find_sources(cfg: Config, folder: Path) -> Discovery:
    """Look (non-recursively) for the mother and child videos in `folder`."""
    d = Discovery()
    mom_p, child_p = cfg.mom_pattern.lower(), cfg.child_pattern.lower()
    for p in sorted(folder.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file() or is_junk_file(p.name) or is_transit_file(p.name):
            continue
        if p.suffix.lower() not in cfg.video_extensions:
            continue
        stem = p.stem.lower()
        is_mom, is_child = mom_p in stem, child_p in stem
        if is_mom and is_child:
            d.both.append(p)
        elif is_mom:
            d.mom.append(p)
        elif is_child:
            d.child.append(p)
    return d


# This detector deliberately does not feed find_sources/the promotion pipeline.
ROLE = re.compile(r"(?<![a-z0-9])(mother|mom|children|child)(\d*)(?![a-z0-9])", re.I)


def discover_field(cfg: Config, participant: str) -> dict:
    """Read-only field inventory. Session boundaries must be explicitly reviewed.

    No media decoding, hashing, readiness inference, or writes. Links/junctions
    are excluded even when their target is inside the participant tree.
    """
    if not re.fullmatch(cfg.field_participant_id_regex, participant):
        raise ValueError("invalid field participant ID")
    authorized = cfg.inbox_dir.resolve(strict=True)
    folder = cfg.inbox_dir / participant
    if folder.is_symlink() or getattr(folder, 'is_junction', lambda: False)():
        raise ValueError("participant root must not be a link/junction")
    root = folder.resolve(strict=True)
    if not root.is_relative_to(authorized) or not root.is_dir():
        raise ValueError("participant outside authorized inbox")
    roots = cfg.field_sessions.get(participant, [])
    result = {"schema": 2, "participant_id": participant, "files": [], "sessions": [],
              "issues": [], "delivery_status": "WaitingForDelivery",
              "integrity_status": "NotVerified", "qc_status": "NotApproved"}
    def issue(code, path, suggestion):
        result['issues'].append(dict(code=code, path=path, suggestion=suggestion))
    stack = [folder]
    while stack:
        directory = stack.pop()
        try:
            if (directory.is_symlink() or getattr(directory, 'is_junction', lambda: False)()
                    or not directory.resolve(strict=True).is_relative_to(root)):
                issue('LINK_EXCLUDED', directory.relative_to(folder).as_posix(), 'Directory changed during scan')
                continue
            entries = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError as exc:
            issue('SCAN_ERROR', directory.relative_to(folder).as_posix(), str(exc))
            continue
        for path in entries:
            rel = path.relative_to(folder).as_posix()
            try:
                meta = path.lstat()
                if (stat.S_ISLNK(meta.st_mode) or
                        getattr(path, 'is_junction', lambda: False)() or
                        getattr(meta, 'st_file_attributes', 0) & 0x400 or
                        not path.resolve(strict=True).is_relative_to(root)):
                    issue('LINK_EXCLUDED', rel, 'Review link/junction outside inventory')
                    continue
                if stat.S_ISDIR(meta.st_mode):
                    stack.append(path)
                    continue
                if not stat.S_ISREG(meta.st_mode):
                    issue('SPECIAL_FILE_EXCLUDED', rel, 'Review non-regular file')
                    continue
                suffix = path.suffix.lower()
                kind = ('Auxiliary360' if suffix in ('.insv', '.lrv') else
                        'AuxiliaryManifest' if suffix == '.json' else
                        'Video' if suffix == '.avi' else 'Other')
                if is_transit_file(path.name):
                    kind = 'TransferInProgress'
                matches = [r for r in roots if Path(rel).is_relative_to(Path(r))]
                session = matches[0] if len(matches) == 1 else None
                # Use only components below the declared session root.
                parts = (Path(rel).relative_to(session).parts if session else Path(rel).parts)
                tokens = [(part, m.group(1).lower(), m.group(2))
                          for part in (*parts[:-1], path.stem) for m in ROLE.finditer(part)]
                roles = {'mom' if role in ('mother', 'mom') else 'child' for _, role, _ in tokens}
                games = {int(n) for _, _, n in tokens if n and len(n) <= 2 and int(n) > 0}
                bad_number = any(n and (len(n) > 2 or int(n) == 0) for _, _, n in tokens)
                codes = []
                if kind == 'Video':
                    if session is None: codes.append('REVIEW_SESSION_UNSPECIFIED')
                    if len(roles) != 1: codes.append('REVIEW_ROLE_CONTRADICTORY' if roles else 'REVIEW_ROLE_UNKNOWN')
                    if len(games) > 1 or bad_number: codes.append('REVIEW_GAME_CONTRADICTORY')
                    elif not games: codes.append('REVIEW_GAME_UNSPECIFIED')
                    words = re.findall(r'[a-z]+', path.stem.lower())
                    aliases = ('mother', 'mom', 'children', 'child')
                    if any(w not in aliases and len(w) >= 4 and
                           difflib.get_close_matches(w, aliases, n=1, cutoff=0.8) for w in words):
                        codes.append('REVIEW_ROLE_TYPO')
                record = dict(relative_path=rel, name=path.name, size=meta.st_size,
                              mtime_ns=meta.st_mtime_ns, kind=kind, session=session,
                              role=next(iter(roles)) if len(roles) == 1 else None,
                              game=next(iter(games)) if len(games) == 1 and not bad_number else None,
                              evidence=[dict(component=p, token=r, attached_number=n) for p, r, n in tokens],
                              review_codes=codes)
                result['files'].append(record)
                if is_transit_file(path.name):
                    issue('TRANSFER_IN_PROGRESS', rel, 'Wait for delivery completion')
            except (OSError, ValueError) as exc:
                issue('SCAN_ERROR', rel, str(exc))
    result['files'].sort(key=lambda f: f['relative_path'])
    # Case-insensitive duplicates are reviewable even across sessions (Windows).
    names = Counter(f['name'].casefold() for f in result['files'] if f['kind'] == 'Video')
    for f in result['files']:
        if f['kind'] == 'Video' and names[f['name'].casefold()] > 1:
            f['review_codes'].append('REVIEW_DUPLICATE_NAME')
        for code in f['review_codes']:
            issue(code, f['relative_path'], 'Review original name, role, session and game; no automatic correction')
    for session in roots:
        files = [f for f in result['files'] if f['session'] == session]
        groups = defaultdict(list)
        for f in files:
            if f['kind'] == 'Video': groups[f['game']].append(f)
        games = []
        for number, candidates in sorted(groups.items(), key=lambda item: (item[0] is None, item[0] or 0)):
            valid = (number is not None and len(candidates) == 2 and
                     {f['role'] for f in candidates} == {'mom', 'child'} and
                     not any(f['review_codes'] for f in candidates) and
                     not any(any(c in f['review_codes'] for c in (
                         'REVIEW_ROLE_UNKNOWN', 'REVIEW_ROLE_CONTRADICTORY',
                         'REVIEW_ROLE_TYPO', 'REVIEW_GAME_CONTRADICTORY')) for f in files))
            games.append(dict(game=number, status='CandidatePair' if valid else 'NeedsReview',
                              review_code=None if valid else ('REVIEW_GAME_UNSPECIFIED' if number is None else 'REVIEW_CANDIDATES'),
                              sources=[f['relative_path'] for f in candidates]))
        result['sessions'].append(dict(session_id=session, games=games,
                                      delivery_status='WaitingForDelivery',
                                      manifest_status='NotChecked', integrity_status='NotVerified', qc_status='NotApproved'))
    # Copy logs have no authoritative schema in the field evidence. Preserve them
    # as auxiliary evidence; never infer completeness from JSON presence.
    for f in result['files']:
        if f['kind'] == 'AuxiliaryManifest':
            # Only our explicit inventory contract is machine comparable. Field
            # copy logs with any other format remain untrusted review evidence.
            try:
                if f['size'] > 1024 * 1024:
                    raise ValueError('manifest exceeds 1 MiB inspection limit')
                manifest_path = folder / f['relative_path']
                if manifest_path.is_symlink() or not manifest_path.resolve().is_relative_to(root):
                    raise ValueError('manifest path changed during scan')
                manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
                if not isinstance(manifest, dict) or manifest.get('schema') != 'rg2019.inventory.v1':
                    raise ValueError('unknown copy-log schema')
                entries = manifest.get('files')
                if not isinstance(entries, list) or f['session'] is None:
                    raise ValueError('manifest requires files list and reviewed session')
                expected = {}
                for entry in entries:
                    if (not isinstance(entry, dict) or not isinstance(entry.get('relative_path'), str)
                            or type(entry.get('size')) is not int or entry['size'] < 0):
                        raise ValueError('invalid manifest entry')
                    name = entry['relative_path']
                    if (name in expected or '\\' in name or ':' in name or name.startswith('/')
                            or any(p in ('', '.', '..') for p in name.split('/'))):
                        raise ValueError('duplicate or unsafe manifest path')
                    expected[name] = entry['size']
                actual = {Path(x['relative_path']).relative_to(f['session']).as_posix(): x['size']
                          for x in result['files'] if x['session'] == f['session'] and x['kind'] == 'Video'}
                mismatch = expected != actual
                f['manifest_evidence'] = dict(expected=expected, observed=actual)
                for s in result['sessions']:
                    if s['session_id'] == f['session']:
                        if mismatch: s['manifest_status'] = 'ManifestMismatch'
                        elif s['manifest_status'] == 'NotChecked': s['manifest_status'] = 'InventoryMatches'
                if mismatch:
                    issue('MANIFEST_MISMATCH', f['relative_path'], 'Reconcile listed AVI paths/sizes with observed files')
            except (OSError, ValueError) as exc:
                issue('REVIEW_MANIFEST_SCHEMA', f['relative_path'], str(exc))
    return result
