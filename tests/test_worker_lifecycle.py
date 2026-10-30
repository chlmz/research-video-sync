import subprocess
import sys
import time

import pytest

from rg2019.synthetic_local import run_worker


def test_deadline_terminates_worker_and_ffmpeg_like_descendant(tmp_path, monkeypatch):
    """Real process tree; descendant stands in for blocked FFmpeg, not a mock PID."""
    heartbeat = tmp_path / 'heartbeat'
    descendant = ('import time; from pathlib import Path; p=Path(' + repr(str(heartbeat)) + '); '
                  'f=p.open("ab", buffering=0);\nwhile True: f.write(b"."); time.sleep(0.05)')
    parent = ('import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",' +
              repr(descendant) + ']); time.sleep(60)')
    original = subprocess.Popen
    workers = []
    def launch(command, **options):
        if 'rg2019.synthetic_worker' in command:
            child = original([sys.executable, '-c', parent], **options)
            workers.append(child)
            return child
        return original(command, **options)
    monkeypatch.setattr(subprocess, 'Popen', launch)
    with pytest.raises(TimeoutError): run_worker(tmp_path, timeout=5)
    assert workers[0].poll() is not None and heartbeat.exists()
    size = heartbeat.stat().st_size
    time.sleep(0.25)
    assert heartbeat.stat().st_size == size
