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

## Milestone 2: delivery contract

`rg2019.delivery` wraps the existing discovery/planner. `template()` produces an
**unapproved** `rg2019.delivery.v1` declaration outside INBOX, with the discovery
inventory digest and per-session expected games and file SHA-256/size, including
auxiliaries. A reviewer must explicitly declare session review and closure, record
evidence, reviewer reference and a timezone-qualified timestamp. Closure is a human
assertion, not proof supplied by a copy log. Hash comparison is computed separately.
Unknown schema, missing/extra files, stale inventory, undeclared games, malformed
declarations and discovery issues block execution. Unknown field JSON stays in
review; a future versioned adapter requires approval of its semantics.

States remain independent: CandidatePair/NeedsReview from discovery;
WaitingForDelivery/DeclaredComplete; NotVerified/IntegrityVerified;
NotRun/technical result; NotApproved for scientific QC. Session/game identity and
original paths/classification evidence remain in each job. Unnumbered games cannot
be authorized by this contract. There is no automatic scientific approval and no
change to the old StateStore or synthetic execution schema.

## Milestone 3: storage protocol

`storage.Inputs` exposes read/verified-copy only. Every input is rehashed after an
exclusive bounded copy, with size/mtime checks and scratch-space reservation.
RAW ingestion always raises. `storage.Results` uses participant / session digest /
game / input fingerprint directories; each contains immutable attempt directories.
`COMMITTED.json` references one manifest by SHA-256. Readers **must** use `inspect()`;
the presence of an MP4 or directory is not a completed result. Manifests identify
the original session text, sources, hashes, parameters, technical status and QC.

This avoids assuming remote rename/lock equivalence. Concurrent writers use
exclusive file creation; matching completed results are idempotent, divergent
results block. A lost acknowledgement after completion is recovered by readback.
An interrupted attempt before completion is retained and a new attempt may finish.
A torn intent/completion record blocks for human investigation: never overwrite,
delete, steal a remote claim or guess that a timeout means the write failed.

The native transport accepts ordinary UNC paths on Windows without mapped drives
or credential management. The integrated entrypoint remains restricted to marked
local synthetic roots. Native SMB exclusive-create behavior, cache visibility,
durability and reconnect semantics are **unvalidated**. Local simulations exercise
failure paths, not Synology guarantees. OS filesystem calls can stall on SMB beyond
application expectations; there is no claim of a hard network-I/O deadline.
Trusted roots and an exclusive operational writer are required; containment checks
do not defend against an adversary swapping reparse points between syscalls.

## Milestone 4: manual integration and monitor interface

`python -m rg2019.preproduction CONFIG {template,plan,run} --participant 000001`
is a manual entrypoint. `run` also requires `--declaration FILE --fingerprint HASH`.
There is no scheduler, batch scan, automatic retry or live mode. Configuration
defaults to disabled; only new, explicitly marked local synthetic workspaces are
accepted. The UNC transport is prepared separately but deliberately unreachable
from live execution until scientific/storage authorization is resolved.

Input copies go into a unique local attempt. The complete delivery is checked
again before launching the existing bounded worker, which reuses `media.py` and
`syncest.py` unchanged. Limits remain synthetic: two AVI inputs, 1 GiB maximum
configurable input (256 MiB default), 120 s media duration, 1080p/60 fps, 600 s
maximum worker deadline (120 s default). Resource requirements for full-length
field recordings remain unapproved. Windows taskkill tree failure or pipes that
remain open produce an explicit operational failure, never technical success.

Local state uses a separate `rg2019.preproduction-state.v1` journal, atomic local
replacement and chained event hashes (corruption detection, not a digital signature).
One local OS lock excludes simultaneous executions sharing the workspace. Up to
three explicit attempts are allowed; conflicts require review. Verified retained
outputs can finish publication without encoding again. Completion is inspected
before retry budgeting so a lost acknowledgement can recover after the last try.
The manifest records commit, dirty flag, Python/OS/tool versions, parameters,
limits, original relative paths and hashes; `sync.json` retains estimator evidence.
TechnicalSuccess/Published never changes scientific QC from NotApproved.

Future monitor contract: stdout JSON for successful template/plan/run, stderr JSON
for errors; exit 0 = command completed (a plan may still contain Blocked jobs),
20 = policy/configuration/delivery blocked, 30 = immutable data conflict requiring
review, 40 = operational/media failure. A process crash may instead use the OS exit
code. Work must read job status, not infer scientific approval from exit 0. No
existing monitor, task, account, credential store or service has been modified.

The prior pipeline and its state stay available unchanged. There is no automatic
migration from old SUCCESS/Published to delivery closure or QC. A new declaration
and verified inventory are required; old states may remain read-only evidence.
