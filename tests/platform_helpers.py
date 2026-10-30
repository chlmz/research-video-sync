"""Narrow capability probes; never hide unexpected filesystem failures."""
import subprocess

import pytest


def symlink_or_skip(link, target, *, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        if getattr(exc, 'winerror', None) == 1314:
            pytest.skip('Windows token lacks symlink privilege (WinError 1314); no elevation required')
        raise


def functional_bash(executable):
    if executable is None:
        return None
    try:
        result = subprocess.run([executable, '-c', 'printf BASH_READY'],
                                capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return executable if result.returncode == 0 and result.stdout == b'BASH_READY' else None
