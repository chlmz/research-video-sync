"""Portable Windows path budgets and conservative storage error reporting."""
import errno
from pathlib import Path


class PathBudgetError(OSError):
    pass


class SourceChanged(ValueError):
    pass


class IntegrityError(ValueError):
    pass


def check_path(path, *, directory=False):
    path = Path(path).absolute()
    limit = 247 if directory else 259
    length = len(str(path).encode('utf-16-le')) // 2
    if length > limit:
        kind = 'directory' if directory else 'file'
        raise PathBudgetError(errno.ENAMETOOLONG,
                              f'{kind} path length {length} exceeds {limit} UTF-16 units; '
                              'use a shorter synthetic root', str(path))
    return path


def error_info(exc):
    """Unknown errors are not advertised as transient. No retry is performed."""
    win = getattr(exc, 'winerror', None)
    number = getattr(exc, 'errno', None)
    if isinstance(exc, PathBudgetError) or win == 206 or number == errno.ENAMETOOLONG:
        kind = 'path_too_long'
    elif isinstance(exc, SourceChanged):
        kind = 'source_changed'
    elif isinstance(exc, IntegrityError):
        kind = 'integrity_error'
    elif isinstance(exc, PermissionError) or win in (5, 32, 33):
        kind = 'access_denied'
    elif isinstance(exc, FileExistsError) or win in (80, 183):
        kind = 'already_exists'
    elif win in (53, 59, 64, 121, 1231, 1232) or number in (
            errno.ECONNRESET, errno.ECONNABORTED, errno.ETIMEDOUT, errno.ENETUNREACH):
        kind = 'transient_io'
    else:
        kind = 'operational_error'
    return dict(kind=kind, errno=number, winerror=win, retryable=kind == 'transient_io')
