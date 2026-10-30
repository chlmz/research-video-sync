"""Local fixture sandbox and bounded scientific worker launcher."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import uuid
from dataclasses import asdict

from .synthetic_plan import contained
from .media import sha256_file


class Sandbox:
    def __init__(self, root):
        self.root = Path(root).absolute()
        if str(root).startswith(('\\\\', '//')) or self.root == Path(self.root.anchor):
            raise ValueError('a dedicated local synthetic directory is required')
        contained(self.root, self.root)
        if (self.root / '.synthetic-only').read_text() != 'RG2019 SYNTHETIC ONLY\n':
            raise ValueError('not a synthetic sandbox')

    @classmethod
    def create(cls, root):
        root = Path(root).absolute()
        contained(root, root)
        if str(root).startswith(('\\\\', '//')):
            raise ValueError('UNC is forbidden')
        root.mkdir(parents=True, exist_ok=False)
        (root / '.synthetic-only').write_text('RG2019 SYNTHETIC ONLY\n')
        for name in ('input', 'scratch', 'published', 'state'):
            (root / name).mkdir()
        return cls(root)

    def path(self, *parts):
        return contained(self.root, self.root.joinpath(*parts))


def process(box, cfg, job, timeout=120, max_bytes=256 * 1024**2):
    """One isolated worker per job; subprocess lifetime bounds FFmpeg and FFT.

    Failed attempts remain in scratch for inspection. No global temp directory.
    """
    if not 0 < timeout <= 600 or not 0 < max_bytes <= 1024**3:
        raise ValueError('invalid operational limits')
    if not 1000 <= cfg.sync.sample_rate <= 48000:
        raise ValueError('unsupported synthetic sample rate')
    if Path(cfg.followup_root).absolute() != box.path('input'):
        raise ValueError('input must be the sandbox input directory')
    if job['status'] != 'Authorized' or set(job['sources']) != {'mom', 'child'}:
        raise ValueError('job is blocked')
    sources = {role: box.path('input', cfg.inbox, job['participant'], rec['path'])
               for role, rec in job['sources'].items()}
    total = sum(p.stat().st_size for p in sources.values())
    if total > max_bytes:
        raise ValueError('synthetic input byte limit exceeded')
    required = max(total * 20, 128 * 1024**2)
    if shutil.disk_usage(box.path('scratch')).free < required:
        raise OSError('insufficient scratch space')
    attempt = box.path('scratch', uuid.uuid4().hex)
    attempt.mkdir()
    for role, src in sources.items():
        dest = attempt / (role + '.avi')
        shutil.copyfile(src, dest)
        if sha256_file(dest) != job['sources'][role]['sha256'] or sha256_file(src) != job['sources'][role]['sha256']:
            raise ValueError('source integrity changed')
    config = asdict(cfg)
    config['followup_root'] = str(box.path('input'))
    (attempt / 'config.json').write_text(json.dumps(config), encoding='utf-8')
    command = [sys.executable, '-m', 'rg2019.synthetic_worker', str(attempt)]
    options = dict(cwd=str(Path(__file__).resolve().parents[1]), stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE, text=True)
    if os.name != 'nt':
        options['start_new_session'] = True
    child = subprocess.Popen(command, **options)
    try:
        _, err = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True, timeout=15)
        else:
            os.killpg(child.pid, signal.SIGKILL)
        child.kill()
        child.communicate()
        raise TimeoutError('scientific worker exceeded deadline')
    if child.returncode:
        raise RuntimeError('scientific worker failed: ' + err[-2000:])
    return attempt / 'outputs'
