# Integrated preproduction (synthetic only)

Branch starts at `7e0703404f560e1533bdf8d93f6cd7f989c7a58b`; PRs #4 and #5
remain unchanged. No production authorization, real media, NAS access or scheduled
execution is part of this implementation.

## Milestone 1: Windows capabilities

The reported Dell WinError 1314 means the non-admin token cannot create symlinks.
Only that exact error skips the symlink fixture. ACL errors and other failures
propagate. Windows separately tests an unprivileged directory junction and checks
that discovery excludes it. POSIX skips only that Windows-specific junction test.
No Developer Mode or elevation is required. The original symlink exclusion still
runs wherever creation is supported. A functional Bash probe distinguishes Git
Bash from an unusable WSL launcher; only the legacy shell regression is optional.
The Python pipeline tests never require Bash. `pytest -ra` lists each omission.
The reported Dell validation is user-provided; its local report is unavailable in
this cloud environment and has not been re-read or rerun on the Dell.
