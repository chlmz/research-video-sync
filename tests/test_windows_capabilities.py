import os
import subprocess

import pytest

from platform_helpers import symlink_or_skip, functional_bash
from rg2019.config import from_dict
from rg2019.discovery import discover_field


def test_only_missing_symlink_privilege_skips():
    class Link:
        def symlink_to(self, *a, **k):
            exc = OSError('privilege unavailable')
            exc.winerror = 1314
            raise exc
    with pytest.raises(pytest.skip.Exception, match='1314'):
        symlink_or_skip(Link(), 'unused')


def test_other_symlink_errors_are_failures():
    class Link:
        def symlink_to(self, *a, **k):
            raise PermissionError('real ACL failure')
    with pytest.raises(PermissionError):
        symlink_or_skip(Link(), 'unused')


def test_unavailable_bash_is_optional(monkeypatch):
    assert functional_bash(None) is None
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, 1, b'WSL unavailable'))
    assert functional_bash('simulated-wsl-launcher') is None


@pytest.mark.skipif(os.name != 'nt', reason='Windows junction API; symlink exclusion runs on POSIX')
def test_windows_junction_excluded_without_symlink_privilege(tmp_path):
    folder = tmp_path / '00_INBOX' / '000001'
    folder.mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'children1.avi').write_bytes(b'synthetic')
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(folder / 'junction'), str(outside)],
                   check=True, capture_output=True)
    try:
        report = discover_field(from_dict({'followup_root': str(tmp_path)}), '000001')
        assert not report['files']
        assert any(i['code'] == 'LINK_EXCLUDED' for i in report['issues'])
    finally:
        os.rmdir(folder / 'junction')
