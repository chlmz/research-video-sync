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
