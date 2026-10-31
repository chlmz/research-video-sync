"""Portable local-selection contract. No media processing or scientific approval."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import stat
import uuid

from .discovery import ROLE, is_transit_file
from .storage import relative, write_new
from .synthetic_plan import contained, digest, plan

SCHEMA = 'rg2019.delivery.v2'
TOOL = 'rg2019-delivery/2.0.0'


def classification(name):
    ext = Path(name).suffix.lower()
    material = 'AVI' if ext == '.avi' else 'Auxiliary360' if ext in ('.insv', '.lrv') else 'HistoricalJSON' if ext == '.json' else 'Other'
    tokens = [m for part in Path(name).with_suffix('').parts for m in ROLE.finditer(part)]
    roles = {'mom' if m[1].lower() in ('mom', 'mother') else 'child' for m in tokens}
    numbers = {int(m[2]) for m in tokens if m[2]}
    role = next(iter(roles)) if material == 'AVI' and len(roles) == 1 else None
    game = next(iter(numbers)) if role and len(numbers) == 1 and 0 < next(iter(numbers)) < 100 else None
    return dict(material=material, role=role, game=game)


def inventory(root):
    root = Path(root).absolute()
    contained(root, root)
    records = {}
    def paths():
        found = {}
        stack = [root]
        while stack:
            directory = stack.pop()
            for p in sorted(directory.iterdir()):
                contained(root, p)
                meta = p.lstat()
                if stat.S_ISDIR(meta.st_mode): stack.append(p)
                elif stat.S_ISREG(meta.st_mode):
                    rel = relative(p.relative_to(root).as_posix())
                    if is_transit_file(p.name): raise ValueError('incomplete transfer: ' + rel)
                    key = rel.casefold()
                    if key in found: raise ValueError('case-insensitive path collision')
                    found[key] = (rel, meta.st_size, meta.st_mtime_ns, meta.st_ino)
                else: raise ValueError('non-regular input')
        return found
    before = paths()
    for rel, size, mtime, ino in before.values():
        p = contained(root, root / rel)
        h = hashlib.sha256()
        count = 0
        with p.open('rb') as handle:
            while chunk := handle.read(1024 * 1024):
                count += len(chunk)
                if count > size: raise ValueError('file grew during hashing')
                h.update(chunk)
        records[rel] = dict(path=rel, size=count, sha256=h.hexdigest(),
                            name=p.name, original_name=None, **classification(rel))
    if paths() != before or any(records[r]['size'] != size for r, size, _, _ in before.values()):
        raise ValueError('selection changed during hashing')
    return records


def identity(document):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, digest({k: v for k, v in document.items() if k != 'delivery_id'})))


def generate(root, *, participant, session_id, closed_at, selection_closed=False, exclusions=None, originals=None):
    if selection_closed is not True: raise ValueError('explicit local selection closure required')
    records = inventory(root)
    exclusions, originals = exclusions or {}, originals or {}
    if not set(exclusions) <= set(records) or not set(originals) <= set(records):
        raise ValueError('trace/exclusion outside selection')
    for rel, old in originals.items():
        records[rel]['original_name'] = relative(old)
    omitted = []
    for rel, reason in sorted(exclusions.items()):
        if not isinstance(reason, str) or not reason.strip(): raise ValueError('exclusion needs justification')
        omitted.append(dict(records.pop(rel), reason=reason))
    doc = dict(schema=SCHEMA, generator_version=TOOL, participant=participant, session_id=session_id,
               closed_at=closed_at, selection_closed=True,
               files=[records[r] for r in sorted(records)], exclusions=omitted)
    doc['delivery_id'] = identity(doc)
    validate(doc)
    return doc


def validate(doc):
    keys = {'schema', 'generator_version', 'participant', 'session_id', 'closed_at',
            'selection_closed', 'files', 'exclusions', 'delivery_id'}
    if not isinstance(doc, dict) or set(doc) != keys or doc['schema'] != SCHEMA:
        raise ValueError('unsupported delivery schema')
    if not isinstance(doc['participant'], str) or not re.fullmatch(r'\d{6}', doc['participant']):
        raise ValueError('participant must be six-digit text')
    if str(uuid.UUID(doc['session_id'])) != doc['session_id']:
        raise ValueError('session must be an independent canonical UUID')
    if datetime.fromisoformat(doc['closed_at']).utcoffset() is None or doc['selection_closed'] is not True:
        raise ValueError('closure must include timezone and explicit declaration')
    if not isinstance(doc['generator_version'], str) or not doc['generator_version'].strip():
        raise ValueError('missing generator version')
    seen = set()
    for group in ('files', 'exclusions'):
        if not isinstance(doc[group], list): raise ValueError('expected file list')
        for record in doc[group]:
            required = {'path', 'name', 'original_name', 'size', 'sha256', 'material', 'role', 'game'}
            if group == 'exclusions': required.add('reason')
            if not isinstance(record, dict) or set(record) != required: raise ValueError('invalid file record')
            path = relative(record['path'])
            if path.casefold() in seen: raise ValueError('path collision')
            seen.add(path.casefold())
            if record['name'] != Path(path).name: raise ValueError('final name mismatch')
            if record['game'] is not None and type(record['game']) is not int: raise ValueError('invalid game type')
            if record['original_name'] is not None: relative(record['original_name'])
            if type(record['size']) is not int or record['size'] < 0 or not isinstance(record['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', record['sha256']):
                raise ValueError('invalid size/hash')
            if any(record[k] != v for k, v in classification(path).items()): raise ValueError('classification conflict')
            if group == 'exclusions' and (not isinstance(record['reason'], str) or not record['reason'].strip()):
                raise ValueError('missing exclusion reason')
    if not doc['files'] or doc['delivery_id'] != identity(doc): raise ValueError('empty selection or delivery identity conflict')


def save(root, destination, doc):
    """External manifest, exclusive create; torn/conflicting evidence is retained."""
    validate(doc)
    root, destination = Path(root).absolute(), Path(destination).absolute()
    contained(destination.parent, destination)
    if destination.resolve().is_relative_to(root.resolve()):
        raise ValueError('manifest must be outside selected scope (no self hashing)')
    if verify(root, doc, participant=doc['participant'], session_id=doc['session_id'])['status'] != 'ReceptionVerified':
        raise ValueError('selection changed before manifest publication')
    try:
        write_new(destination, doc)
    except FileExistsError:
        if json.loads(destination.read_text(encoding='utf-8')) != doc:
            raise ValueError('existing manifest conflict; never overwritten')
    return destination


def verify(root, doc, *, participant, session_id):
    result = dict(status='NeedsReview', integrity_status='NotVerified', qc_status='NotApproved',
                  processing_authorized=False, issues=[])
    try:
        validate(doc)
        if doc['participant'] != participant or doc['session_id'] != session_id:
            raise ValueError('receiver session/participant identity conflict')
        expected = {r['path']: r for r in doc['files'] + doc['exclusions']}
        required = {r['path'] for r in doc['files']}
        scope = Path(root).absolute()
        contained(scope, scope)
        if not scope.exists():
            result.update(status='WaitingForDelivery', missing=sorted(required), additional=[], mismatches=[])
            return result
        observed = inventory(root)
        missing, additional = sorted(required - set(observed)), sorted(set(observed) - set(expected))
        bad = sorted(p for p in set(expected) & set(observed) if any(
            expected[p][k] != observed[p][k] for k in ('size', 'sha256')))
        result.update(missing=missing, additional=additional, mismatches=bad, delivery_id=doc['delivery_id'])
        if bad:
            result.update(status='IntegrityError', integrity_status='Failed')
        elif additional: result['status'] = 'NeedsReview'
        elif missing: result['status'] = 'WaitingForDelivery'
        else: result.update(status='ReceptionVerified', integrity_status='IntegrityVerified')
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        result['issues'].append(type(exc).__name__ + ': ' + str(exc))
    return result


def reception_plan(cfg, participant, session_root, doc, *, session_id, session_reviewed=False):
    """Receipt is not a processing approval; reuse existing planner conservatively."""
    root = contained(cfg.inbox_dir / participant, cfg.inbox_dir / participant / relative(session_root))
    receipt = verify(root, doc, participant=participant, session_id=session_id)
    reviewed = [session_root] if session_reviewed is True and receipt['status'] == 'ReceptionVerified' else []
    jobs = plan(cfg, participant, reviewed_sessions=reviewed)
    jobs = [j for j in jobs if j['session'] == session_root]
    for job in jobs:
        job.update(session_id=session_id, receipt=receipt, status='Blocked', qc_status='NotApproved')
        job['reasons'] = sorted(set(job['reasons'] + ['ScientificProcessingAuthorizationRequired']))
    return dict(receipt=receipt, jobs=jobs)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['generate', 'verify'])
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--participant', required=True)
    p.add_argument('--session-id', required=True)
    p.add_argument('--closed-at')
    p.add_argument('--closed', action='store_true')
    p.add_argument('--selection-metadata', type=Path, help='JSON with exclusions and originals mappings')
    args = p.parse_args(argv)
    try:
        if args.action == 'generate':
            metadata = json.loads(args.selection_metadata.read_text(encoding='utf-8')) if args.selection_metadata else {}
            doc = generate(args.root, participant=args.participant, session_id=args.session_id,
                           closed_at=args.closed_at, selection_closed=args.closed, **metadata)
            save(args.root, args.manifest, doc)
            print(json.dumps(doc, sort_keys=True))
            return 0
        doc = json.loads(args.manifest.read_text(encoding='utf-8'))
        result = verify(args.root, doc, participant=args.participant, session_id=args.session_id)
        print(json.dumps(result, sort_keys=True))
        return 0 if result['status'] == 'ReceptionVerified' else 20
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(json.dumps(dict(status='NeedsReview', error=str(exc))))
        return 20


if __name__ == '__main__':
    raise SystemExit(main())
