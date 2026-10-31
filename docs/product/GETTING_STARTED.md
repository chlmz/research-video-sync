# Getting started — human guide (synthetic only)

> **Current scope:** reproducible local demonstration using invented audio/video and file trees. This is **not** authorization to run the historical live pipeline or operate on cohort participants. Code reviewed against `a21279d6c7313d65eb1239e70f1bae3ae62b1420` (PR #7). Commands below follow the repository entrypoints; live deployment has not been validated.

## Audience and expected result

This guide is for a researcher or analyst who wants to understand and evaluate the video synchronization software *without any research data*. You will:

1. Install the Python dependencies and FFmpeg.
2. Run the automated synthetic test suite.
3. Generate simulated mother/child recordings and exercise the guarded, recoverable preproduction worker.
4. Optionally generate and verify a `delivery.v2` manifest of the invented input set.
5. Inspect the outputs while keeping scientific QC explicitly **NotApproved**.

The synthetic demo creates two unnumbered layouts that remain blocked, and three numbered jobs across reviewed sessions that publish locally after a simulated interrupted run. It verifies a known 2-second offset. **It does not produce a side-by-side for every job and does not process real field data.**

## Prerequisites

- Git and Python 3.12 (the CI baseline).
- FFmpeg and FFprobe available on `PATH`, including an H.264 encoder (libx264), AAC encoder and test media support.
- A new, local, **empty/nonexistent** directory for the synthetic demo; not a network/UNC path, synced research folder or working source directory.
- Enough local free space for generated AVI, scratch, encoded MP4, retained diagnostic attempts and tests.

Versions beyond the CI baseline may work, but are not guaranteed by this documentation.

## Step 1 — obtain the review code

Open a terminal in the project repository.

```bash
git clone https://github.com/chlmz/research-video-sync.git
cd research-video-sync
git fetch origin codex/gpis-delivery-v2
git switch --detach a21279d6c7313d65eb1239e70f1bae3ae62b1420
git rev-parse HEAD
```

**Why a detached commit?** The repository's default branch predates the stacked development PRs. Checking out the exact verified SHA makes the example reproducible. When a later reviewed release exists, replace this commit with its release tag.

## Step 2 — install the tools

On **Windows PowerShell**:

```powershell
py -3.12 -m venv .venv
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -r requirements-dev.txt
& $py --version
ffmpeg -version
ffprobe -version
```

On **Linux/macOS**:

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements-dev.txt
./.venv/bin/python --version
ffmpeg -version
ffprobe -version
```

If Python, FFmpeg or FFprobe is absent, install it using your normal organization-approved package mechanism. Do not change machine-wide service accounts or scheduled tasks just for the demo.

## Step 3 — run the tests

PowerShell:

```powershell
& $py -m pytest -ra
```

Linux/macOS:

```bash
./.venv/bin/python -m pytest -ra
```

On the commit above, GitHub Actions run `41157402895` reported Windows **296 passed** and Ubuntu **295 passed, one Windows-specific skip**. Those counts are a historical reference, **not an assertion about your local run or a newer branch**. Review your actual test summary and the reason for any skip. Do not add subset-test counts to the total.

## Step 4 — run the synthetic demonstration

Choose a **new, nonexistent** directory; do not reuse a previous demo path. Example commands:

PowerShell:

```powershell
& $py examples/preproduction_demo.py --root "$env:TEMP\rg2019-preproduction-demo-NEW"
```

Linux/macOS:

```bash
./.venv/bin/python examples/preproduction_demo.py --root /tmp/rg2019-preproduction-demo-NEW
```

Replace `NEW` with a new unique identifier each time. A repeat using an existing root should fail rather than erase evidence.

Expected outcome from the demonstration *as implemented*: JSON reporting two deliberately blocked unnumbered layouts, three locally published numbered jobs, interrupted-publication recovery, unchanged original fixtures and `qc_status: NotApproved`. The exact generated paths are printed. Open the reported `sync.json` to inspect the estimated offset and the synthetic reference; do not mark it scientific QC approved.

You may also run the separate earlier phase-2 demonstration:

```powershell
& $py examples/synthetic_demo.py --root "$env:TEMP\rg2019-phase2-demo-NEW"
```

Its success demonstrates synthetic crash recovery; it is not proof that real videos synchronize.

## Step 5 — demonstrate the independent delivery manifest

The guarded preproduction demo generates a synthetic source tree. Use one of its own session scopes as the selected root. This example uses the invented numbered session `000003 / delivery-A`:

PowerShell (adjust `$demo` to the actual **fresh directory** you created):

```powershell
$demo = "$env:TEMP\rg2019-preproduction-demo-NEW"
$selection = Join-Path $demo "00_INBOX\000003\delivery-A"
$manifest = Join-Path $demo "invented-delivery-v2.json"
& $py -m rg2019.delivery_v2 generate --root $selection --manifest $manifest --participant 000003 --session-id "00000000-0000-0000-0000-000000000003" --closed-at "2026-01-01T00:00:00+00:00" --closed
& $py -m rg2019.delivery_v2 verify --root $selection --manifest $manifest --participant 000003 --session-id "00000000-0000-0000-0000-000000000003"
```

The chosen date, UUID, ID and scope are **invented example values**, not a scheme for assigning real study sessions. The manifest must be stored **outside** the selected tree. Generation reads/hashes the whole selection; verification checks expected paths, size and SHA-256. If a file changes or the manifest declares the wrong set, verification is blocked. A status of `ReceptionVerified` means receipt/integrity only; `processing_authorized` remains false, and QC remains `NotApproved`.

## What not to execute

**Do not run** `python pipeline_rg2019.py --config config.json` against a field directory from this guide. That legacy live command can **move 00_INBOX contents to 01_RAW** and assumes an older folder model. Do not use `sync_research_project.sh` or `sync_videos.sh` on real files; they have documented correctness and data-safety bugs. Do not change flags in the synthetic worker to force real inputs.

The preproduction CLI `python -m rg2019.preproduction ...` is also **synthetic-only**, requires a specially initialized workspace and explicit approvals, and is not a supported live ingestion command.

## Troubleshooting

| Symptom | Meaning / action |
|---|---|
| `ffmpeg` or `ffprobe` missing | Install/point to approved FFmpeg and re-run tool check |
| Python import error | Use the specific venv interpreter; install `requirements-dev.txt` |
| Demo refuses a directory | Use a new path, not an existing tree; never delete previous evidence merely to pass |
| A candidate pair remains blocked | Expected for unresolved session/game/receipt in a conservative demo |
| `NotApproved` after successful encoding | Expected; scientific QC is a separate human-authorized state |
| Side-by-side absent from safe demo | Expected; the guarded demo produces paired MP4, and the side-by-side exists in the older API but is not integrated into this safe flow |
| Low audio correlation / no offset | Do not lower thresholds blindly or accept the largest peak without independent evidence |
| AVI H.264 warnings | Inspect actual decoding and timestamp integrity; an AVI extension or warning alone is not evidence of irrecoverable corruption |

## Further reading

- [Scientific method and confidence/QC](SCIENTIFIC_METHOD.md)
- [Delivery v2 specification](../DELIVERY_V2.md)
- [Preproduction runbook and limits](../PREPRODUCTION.md)
- [Field discovery semantics](../FIELD_DISCOVERY.md)
- [Safe adaptation instructions for AI assistants](AI_ADAPTATION_GUIDE.md)
- [Release and scientific-product checklist](RELEASE_CHECKLIST.md)
