# Work: controlled Dell validation, no deployment

Use a standard non-admin account. Do not change Developer Mode, ACLs, services,
credentials, scheduled tasks, existing installations or scientific folders. This
procedure tests only a fresh local synthetic workspace. No NAS command is included.

## Obtain and isolate the exact revision

From an existing clone, fetch the review branch and create a detached worktree at
the final SHA recorded in the review report. Use a NEW path for each validation:

```powershell
git fetch origin codex/gpis-preproduction-integration
git rev-parse origin/codex/gpis-preproduction-integration
# Replace REVIEW_SHA with the independently checked full SHA, not a mutable branch.
git worktree add --detach C:\GPIS\temp\preproduction-review REVIEW_SHA
Set-Location C:\GPIS\temp\preproduction-review
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe --version
ffmpeg -version
ffprobe -version
ffmpeg -nostdin -v error -f lavfi -i testsrc=size=160x120:rate=10 -f lavfi -i sine=frequency=440 -t 1 -c:v libx264 -pix_fmt yuv420p -c:a aac -f null -
```

Record executable paths using `Get-Command ffmpeg,ffprobe` and the SHA. Do not
replace Dell tools automatically. If commands fail, report the missing dependency.
The example service configuration uses ordinary absolute paths and PATH executable
lookup, never a personal profile. For reproducibility, an operator may supply
approved absolute FFmpeg/FFprobe executable paths in a local configuration.

## Validate and preserve evidence

```powershell
.\.venv\Scripts\python.exe -m pytest -ra --junitxml=C:\GPIS\temp\preproduction-full.xml
$fullExit = $LASTEXITCODE
.\.venv\Scripts\python.exe -m pytest -ra tests/test_windows_capabilities.py tests/test_delivery_contract.py tests/test_storage.py tests/test_preproduction.py tests/test_preproduction_e2e.py tests/test_worker_lifecycle.py tests/test_windows_storage_regression.py --junitxml=C:\GPIS\temp\preproduction-specific.xml
$specificExit = $LASTEXITCODE
.\.venv\Scripts\python.exe examples/preproduction_demo.py --root C:\GPIS\temp\preproduction-fixtures-new
$demoExit = $LASTEXITCODE
Write-Output "full=$fullExit specific=$specificExit demo=$demoExit"
```

Use unique report and fixture paths if they already exist; do not remove prior
evidence to make a run succeed. The demo refuses an existing root. It generates
AVI files locally, two unnumbered layouts that remain blocked, and three numbered
games across independent sessions. It injects an interruption after completion,
recovers without a second encoding and checks original bytes/mtimes and a known
two-second offset. Manifests retain NotApproved QC.

The specific suite is a subset of the full suite: never add its count to the full
total. Report collected/passed/failed/error/skipped separately, with skip reasons.
On ordinary Windows, WinError 1314 may skip only the symlink fixture. The junction
test must still run. Missing/nonfunctional Bash may skip only the legacy Bash test
in the full suite. Neither skip means that a security or Python pipeline test
passed. Unexpected junction/ACL/process/FFmpeg errors must be investigated.

Review `state/*.json` event chains, manifests, tools/commit provenance and worker
timeout evidence. Confirm no descendant continues writing after termination. Record
open-file sharing errors and antivirus interactions without disabling protections.
Do not manually mark scientific QC approved or copy fixture output to NAS.

## Before any later real-storage validation

### Dell compatibility correction

The a1b7fbd baseline failed locally with 233 pass / 10 fail / 2 skip, and the
specific suite with 39 pass / 11 fail (46 / 4 under a short root). Directory
creation failed at 248 UTF-16 units, ordinary file access at 260; FFmpeg/FFprobe
9.0.2 handled the tested 320-character file paths. Do not enable LongPathsEnabled
to conceal this regression. The compact v2 layout and preflight now handle these
constraints; the 21 new regression cases include forced identity collisions,
long roots, exact injected-disconnect checkpoints, immutable existing results,
UTF-16 boundaries, permanent-error review and manual transient recovery.

For a fresh Dell run, choose a NEW short root such as
`C:\GPIS\temp\v6-YYYYMMDD-HHMMSS`. Clone the PR branch there, check out the exact
review SHA, and create a dedicated venv. If `py` is unavailable, the already
prepared `C:\GPIS\services\tools\python312\python.exe` can create that venv;
do not install into the service venv or change PATH globally. Use the venv Python
explicitly. Put `--basetemp`, JUnit files and demo root under this new directory,
with different paths for full/specific runs. A second equivalent-long-root run
can confirm the path regression; do not reuse/delete prior evidence.

The full current suite has 266 cases (245 prior + 21 new), and the specific
selection above has 71 (50 prior + 21 new). On this non-admin Dell, only the
symlink privilege fixture and legacy Bash test may skip in the full suite;
junction and all 71 specific tests must run. CI capability differences may yield
266 pass on Windows and 265 pass / one junction skip on Linux. Record actual
counts and reasons, never infer these from expected values.

### Reuse the approved SMB mechanism in Work

The 29 October prelogin synthetic task under `GPIS-SERVER\gpis_runner` passed
with exit 0, confirmed by local/NAS run ID and hashes. Its existing wrapper uses
DPAPI LocalMachine and nonpersistent New-SmbMapping for
`DS423GPIS\gpis_server`. A later interactive Credential Manager / LogonUserW
type-9 experiment received 1326; it used a different credential source and logon
context. That does **not** establish a regression of the approved service access
or justify a password change. Its ultimate authentication cause remains unproven.

Current non-admin task inspection/re-execution was denied. Work must use the
already approved wrapper and technical identity from an authorized context,
preserving prior task state, without creating replacement tasks, extracting
secrets, or changing accounts/ACLs. Record identity, method, phase, errno and
winerror separately. Storage primitive tests belong only in a fresh namespace
under the authorized `GPIS_SERVER/infra-tests`; the scientific entrypoint still
rejects UNC. No real SMB/service-account validation is part of these code tests.

A separate human authorization is required. Use a disposable, non-scientific SMB
test location approved by its administrator, never official INBOX/RAW or existing
results. First establish minimal ACLs, a single writer and the no-overwrite policy.
Test exclusive creation under competing clients, partial writes, cache visibility,
readback hashes, disconnect before/after commit, torn records, service-account
authentication without mapped drives and SMB stalls. Interrupted/torn commits must
remain blocked; do not "fix" them by deleting locks or overwriting result records.
Compare server/client observations before making any durability claim. There are
no automated commands here to perform that validation or alter ACLs.

After technical review, scientific approval is still needed for session boundaries,
game numbering, closure evidence/field JSON semantics, accepted integrity source,
full-recording resource limits and QC acceptance/rejection thresholds. Real-data
execution, 02_SYNCED/99_LOGS_QC writes and scheduling remain separately blocked.
The shipped entrypoint has no live mode; enabling one requires a reviewed change,
not changing `enabled` to true in the synthetic configuration.
