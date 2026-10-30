"""Single-job, manually invoked synthetic integration. No scheduler or live mode."""
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import uuid

from .config import from_dict
from .delivery import delivery_plan, template
from .media import sha256_file
from .storage import Inputs, Results, Conflict, is_unc, validate_root, OUTPUTS, write_new
from .synthetic_plan import contained, digest
from .synthetic_publish import exclusive
from .synthetic_local import run_worker
from .fs_errors import check_path, error_info, SourceChanged

MARKER = 'RG2019 SYNTHETIC PREPRODUCTION ONLY\n'


def preflight_workspace(root):
    """Generated paths including journal replacement and worker intermediates."""
    for name in ('00_INBOX', '02_SYNCED', 'scratch', 'state'):
        check_path(root / name, directory=True)
    for name in ('execution.lock', 'f' * 64 + '.json', 'f' * 32 + '.tmp'):
        check_path(root / 'state' / name)
    attempt = root / 'scratch' / ('f' * 32)
    check_path(attempt / 'outputs', directory=True)
    for name in ('mom.avi', 'child.avi', 'mom.pcm', 'child.pcm', 'config.json'):
        check_path(attempt / name)
    for name in OUTPUTS:
        check_path(attempt / 'outputs' / name)


class Blocked(ValueError):
    pass


@dataclass
class Settings:
    workspace: str
    enabled: bool = False
    mode: str = 'synthetic'
    max_input_bytes: int = 256 * 1024**2
    reserve_bytes: int = 128 * 1024**2
    timeout_seconds: int = 120
    max_attempts: int = 3

    def validate(self, *, execute=False):
        # Check policy before any path access: real/UNC execution has no switch.
        if self.mode != 'synthetic' or is_unc(self.workspace):
            raise Blocked('live/UNC execution blocked pending controlled authorization and SMB validation')
        if execute and self.enabled is not True:
            raise Blocked('execution disabled by default')
        if not (type(self.enabled) is bool and type(self.max_input_bytes) is int and
                0 < self.max_input_bytes <= 1024**3 and type(self.reserve_bytes) is int and
                self.reserve_bytes >= 128 * 1024**2 and type(self.timeout_seconds) is int and
                0 < self.timeout_seconds <= 600 and type(self.max_attempts) is int and 1 <= self.max_attempts <= 3):
            raise Blocked('invalid operational limits')
        root = validate_root(self.workspace)
        preflight_workspace(root)
        if contained(root, root / '.gpis-synthetic-only').read_text(encoding='utf-8') != MARKER:
            raise Blocked('unmarked synthetic workspace')
        for name in ('00_INBOX', '02_SYNCED', 'scratch', 'state'):
            if not contained(root, root / name).is_dir():
                raise Blocked('incomplete synthetic workspace')
        return root


def initialize(root):
    """Create a NEW local fixture workspace, never adopt existing scientific data."""
    if is_unc(root):
        raise Blocked('UNC initialization forbidden')
    root = validate_root(root)
    preflight_workspace(root)
    contained(root, root)
    root.mkdir(parents=True, exist_ok=False)
    (root / '.gpis-synthetic-only').write_text(MARKER, encoding='utf-8')
    for name in ('00_INBOX', '02_SYNCED', 'scratch', 'state'):
        (root / name).mkdir()
    return root


def validate_pipeline(root, cfg):
    if Path(cfg.followup_root).absolute() != root or cfg.inbox_dir.absolute() != root / '00_INBOX':
        raise Blocked('pipeline input outside marked fixture root')
    if not 1000 <= cfg.sync.sample_rate <= 48000:
        raise Blocked('sample rate outside bounded worker limits')


def provenance(cfg, settings):
    repo = Path(__file__).resolve().parents[1]
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, check=True,
                            capture_output=True, text=True, timeout=10).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=repo,
                           check=True, capture_output=True, text=True, timeout=10).stdout != ''
    versions = {}
    for name in ('ffmpeg', 'ffprobe'):
        result = subprocess.run([getattr(cfg, name), '-version'], check=True,
                                capture_output=True, text=True, timeout=10)
        versions[name] = result.stdout.splitlines()[0]
    return dict(commit=commit, dirty=dirty, python=sys.version, platform=platform.platform(),
                tools=versions, sync=asdict(cfg.sync), encode=asdict(cfg.encode), limits=asdict(settings))


def save_state(path, state):
    check_path(path)
    temp = contained(path.parent, path.parent / (uuid.uuid4().hex + '.tmp'))
    write_new(temp, state)
    os.replace(temp, path)  # Local journal only; never used as an SMB guarantee.


def verify_state(state):
    previous = None
    if type(state.get('attempts')) is not int or not 0 <= state['attempts'] <= 3 or state.get('qc_status') != 'NotApproved':
        raise Conflict('invalid execution state')
    if not isinstance(state.get('events'), list):
        raise Conflict('invalid journal events')
    for event in state['events']:
        if not isinstance(event, dict):
            raise Conflict('invalid journal event')
        value = {k: v for k, v in event.items() if k != 'hash'}
        if value.get('previous') != previous or digest(value) != event.get('hash'):
            raise Conflict('journal integrity mismatch')
        previous = event['hash']
    if 'outputs' in state and set(state.get('output_hashes', {})) != OUTPUTS:
        raise Conflict('invalid retained output records')


def run(settings, cfg, participant, fingerprint, declaration, *, checkpoint=lambda _: None):
    root = settings.validate(execute=True)
    validate_pipeline(root, cfg)
    state_root = root / 'state'
    with exclusive(contained(root, state_root / 'execution.lock')):
        jobs = delivery_plan(cfg, participant, declaration)
        job = next((j for j in jobs if j['fingerprint'] == fingerprint), None)
        if job is None or job['status'] != 'Authorized':
            raise Blocked('delivery authorization blocked or stale')
        results = Results(root / '02_SYNCED')
        results.preflight(job)  # Before attempts, source copies or scientific work.
        state_path = contained(root, state_root / (fingerprint + '.json'))
        try:
            state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else dict(
                schema='rg2019.preproduction-state.v1', job_digest=digest(job), attempts=0,
                technical_status='NotRun', qc_status='NotApproved', events=[])
        except json.JSONDecodeError as exc:
            raise Conflict('torn journal requires review') from exc
        if not isinstance(state, dict) or state.get('schema') != 'rg2019.preproduction-state.v1' or state.get('job_digest') != digest(job):
            raise Conflict('journal identity/schema conflict')
        verify_state(state)
        def record(status, detail=''):
            state['technical_status'] = status
            event = dict(time=datetime.now(timezone.utc).isoformat(), status=status, detail=detail,
                         previous=state['events'][-1]['hash'] if state['events'] else None)
            event['hash'] = digest(event)
            state['events'].append(event)
            save_state(state_path, state)
        try:
            if state['technical_status'] == 'Conflict':
                raise Conflict('previous conflict requires human review')
            existing = results.inspect(job)
            if existing:
                record('Published', 'verified recovery; scientific QC remains NotApproved')
                return existing
            if state['technical_status'] == 'ReviewRequired':
                raise Blocked('previous permanent error requires explicit review')
            if state['attempts'] >= settings.max_attempts:
                raise Blocked('retry budget exhausted; explicit review required')
            state['attempts'] += 1
            record('Running')
            # Reuse a fully hashed local output after a publication disconnect.
            outputs = None
            if 'outputs' in state:
                candidate = contained(root / 'scratch', root / state['outputs'])
                if all(contained(root, candidate / n).is_file() and
                       sha256_file(candidate / n) == h for n, h in state['output_hashes'].items()):
                    outputs = candidate
                else:
                    raise Conflict('retained output changed; no silent re-encoding')
            if outputs is None:
                state['provenance'] = provenance(cfg, settings)
                attempt = root / 'scratch' / uuid.uuid4().hex
                Inputs(cfg.inbox_dir).copy_pair(job, attempt, max_bytes=settings.max_input_bytes,
                                               reserve_bytes=settings.reserve_bytes)
                checkpoint('after_ingest')
                # Revalidate complete delivery after copy, before processing.
                current = delivery_plan(cfg, participant, declaration)
                if job not in current:
                    raise SourceChanged('delivery changed during ingestion')
                worker_cfg = asdict(cfg)
                worker_cfg['followup_root'] = str(root)
                write_new(attempt / 'config.json', worker_cfg)
                outputs = run_worker(attempt, settings.timeout_seconds)
                state['outputs'] = outputs.relative_to(root).as_posix()
                state['output_hashes'] = {n: sha256_file(contained(root, outputs / n)) for n in OUTPUTS}
                record('TechnicallyValidated')
            final = results.publish(job, outputs, state['provenance'], checkpoint=checkpoint)
            record('Published')
            return final
        except Exception as exc:
            if isinstance(exc, Blocked) and state['technical_status'] == 'ReviewRequired':
                raise  # Preserve the original permanent cause and attempt count.
            info = error_info(exc)
            if isinstance(exc, Conflict):
                info.update(kind='conflict', retryable=False)
            state['last_error'] = info
            permanent = info['kind'] in ('path_too_long', 'access_denied', 'already_exists',
                                         'source_changed', 'integrity_error')
            status = 'Conflict' if isinstance(exc, Conflict) else (
                'ReviewRequired' if permanent or state['technical_status'] == 'ReviewRequired' else 'Failed')
            record(status, type(exc).__name__ + ': ' + str(exc))
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('action', choices=['template', 'plan', 'run'])
    parser.add_argument('--participant', required=True)
    parser.add_argument('--declaration', type=Path)
    parser.add_argument('--fingerprint')
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.config.read_text(encoding='utf-8-sig'))
        if set(data) != {'execution', 'pipeline'}:
            raise Blocked('config requires execution and pipeline sections')
        settings = Settings(**data['execution'])
        root = settings.validate(execute=args.action == 'run')
        cfg = from_dict(dict(data['pipeline'], followup_root=str(root)))
        validate_pipeline(root, cfg)
        if args.action == 'template':
            result = template(cfg, args.participant)
        else:
            if args.declaration is None:
                raise Blocked('explicit delivery declaration required')
            declaration = json.loads(args.declaration.read_text(encoding='utf-8-sig'))
            if args.action == 'plan':
                result = delivery_plan(cfg, args.participant, declaration)
            else:
                if not args.fingerprint:
                    raise Blocked('exactly one explicit job fingerprint required')
                result = dict(output=str(run(settings, cfg, args.participant, args.fingerprint, declaration)),
                              technical_status='Published', qc_status='NotApproved')
        print(json.dumps(result, sort_keys=True))
        return 0
    except Conflict as exc:
        code, message = 30, str(exc)
        info = dict(error_info(exc), kind='conflict')
    except (Blocked, ValueError, TypeError) as exc:
        code, message = 20, str(exc)
        info = error_info(exc)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        code, message = 40, str(exc)
        info = error_info(exc)
    print(json.dumps(dict(exit_code=code, error=message, qc_status='NotApproved', **info)), file=sys.stderr)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
