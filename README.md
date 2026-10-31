# RG2019 Research Video Synchronization Pipeline

**A reproducible research-software project for synchronizing dual-camera mother–child interaction recordings**, developed in the context of the **2019 Rio Grande Birth Cohort (Coorte de Nascimentos de Rio Grande 2019)**.

**Status: research preview / documentation in progress — NOT approved for unattended real-data processing.** The source repository is public, but actual cohort recordings, internal network details and operational credentials are private. A verified field-scientific synchronization and a released package are still pending.

> **Important for humans and AI agents:** the historic `pipeline_rg2019.py` entrypoint has older **live INBOX → RAW move semantics** and must **not** be run on the current field NAS layout. The newer safeguarded executor is deliberately **synthetic-only**. Follow the [safe quickstart](docs/product/GETTING_STARTED.md), not the old deployment instructions.

## What this project aims to solve

Two research cameras may capture the same event while starting at different times. We need to find the correct mother/child pairing for **each participant, session and game**, estimate the temporal offset using shared audio, trim the camera that started first, export traceable derived videos and independently check scientific alignment.

The intended outputs after full approval are:

- Synchronized mother-view MP4.
- Synchronized child-view MP4.
- Side-by-side MP4 to support visual QC and behavioral coding.
- Machine-readable provenance, audio-offset diagnostics, file-integrity evidence, processing state and QC disposition.

The **safe synthetic worker currently produces the first two MP4s and `sync.json`**; the side-by-side encoder exists in the older media API but has **not yet been integrated into the guarded end-to-end executor**. The definitive output path convention must incorporate **participant + session + game** to avoid collisions; this is pending production design approval.

## Who should read what?

| Reader | Start here | What you will learn |
|---|---|---|
| Researcher / operator | **[Getting started](docs/product/GETTING_STARTED.md)** | Install dependencies, run tests and execute a completely invented, local synthetic demonstration |
| Epidemiologist / methods reviewer | **[Scientific method and QC](docs/product/SCIENTIFIC_METHOD.md)** | Mathematical offset, confidence gates, empirical limitations and validation requirements |
| AI assistant / developer | **[AI adaptation guide](docs/product/AI_ADAPTATION_GUIDE.md)** | Exact code-reading order, invariants, test contract and reusable implementation instructions |
| Data steward / collaborator | **[Public/private policy](docs/product/PUBLIC_PRIVATE_POLICY.md)** | What may and may not go into GitHub |
| Product reporting / publication | **[Release checklist](docs/product/RELEASE_CHECKLIST.md)** | Requirements for a citable, versioned scientific technical product |
| Technical historian | **[Engineering journal](docs/VIDEO_SYNC_ENGINEERING_JOURNAL_WIP.md)** | Dates, SHAs, historical bugs, attempts, decisions and lessons learned |
| Infrastructure architect | **[Public-safe architecture](docs/GPIS_INFRASTRUCTURE_ARCHITECTURE_WIP.md)** | Conceptual data path and role separation, without private network details |

Additional implementation specifications: [field discovery](docs/FIELD_DISCOVERY.md), [delivery contract v2](docs/DELIVERY_V2.md), [guarded preproduction](docs/PREPRODUCTION.md), [synthetic harness](docs/SYNTHETIC_PIPELINE.md), [legacy audit](docs/LEGACY_AUDIT.md), and [storage permission design](docs/STORAGE_PERMISSIONS.md).

## Conceptual pipeline

```text
Dual research cameras (mother / child / auxiliary)
                |
                v
 Field selection + definitive names + closure declaration [FUTURE FIELD ADAPTER]
                |
                v
 Research NAS 00_INBOX + external delivery manifest
                |
           Verify all declared files / SHA-256
                |
                v
  Review participant + session UUID + game pairing
                |
             [EXPLICIT AUTHORIZATION]
                v
    Read-only originals → local scratch copy
                |
        FFmpeg audio extraction
                |
      Offset search → independent confidence/QC
                |
        Trim correct camera → encode MP4
                |
      Two views + side-by-side + provenance
                |
       [TECHNICAL QC + SCIENTIFIC QC]
                v
   Verified publication and logs, no overwrite
```

**Legend:** not all steps shown above are implemented or live. See the [release gate](docs/product/RELEASE_CHECKLIST.md) and [actual status](#actual-implementation-and-validation-status). No direct network address, account or access method is specified in this public design.

### Five states that must remain independent

**Discovery → Receipt → Integrity → Technical processing → Scientific QC/authorization.** A pair that looks plausible is not automatically a complete delivery. `ReceptionVerified` is not `QCApproved`. A file named `COMMITTED.json` does not certify scientific synchronization, even if all bytes are intact. Scientific reviewers must approve criteria and outcomes independently.

### Correct sign convention (do not reverse)

For the same sound event:

```text
offset = event_time_inside_mother_video - event_time_inside_child_video

offset > 0  → mother video started earlier → trim mother at its beginning
offset < 0  → child video started earlier  → trim child at its beginning
offset = 0  → neither leading edge needs trimming
```

The algorithm currently assumes **constant lag**, not clock-drift correction. A difference between the two **recording durations is not evidence of the start offset**.

## Quick, safe evaluation

Requirements: **Python 3.12**, `ffmpeg`, `ffprobe` (with H.264/AAC functionality) and Git. Use a virtual environment. The code below deliberately uses a **pinned review commit** containing the documented synthetic features. The default `main` branch is older than the stacked draft PRs.

```bash
git clone https://github.com/chlmz/research-video-sync.git
cd research-video-sync
git fetch origin codex/gpis-delivery-v2
git switch --detach a21279d6c7313d65eb1239e70f1bae3ae62b1420

python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements-dev.txt
./.venv/bin/python -m pytest -ra
./.venv/bin/python examples/preproduction_demo.py --root /tmp/rg2019-new-synthetic-demo
```

Those shell commands target Linux/macOS. On Windows, use the matching [PowerShell instructions](docs/product/GETTING_STARTED.md). The demo root must be **new and local**. The demo generates artificial recordings, verifies known 2-second offsets for resolvable pairs, deliberately blocks ambiguous cases, and exercises publication recovery. It does **not** validate actual cohort data.

### Optional: receipt-contract CLI

`rg2019.delivery_v2` provides a manifest generator/verifier for **synthetic locally selected files**:

```text
python -m rg2019.delivery_v2 generate --root SYNTHETIC_SELECTION --manifest EXTERNAL_MANIFEST.json --participant 000001 --session-id CANONICAL_SESSION_UUID --closed-at ISO_TIMESTAMP_WITH_OFFSET --closed

python -m rg2019.delivery_v2 verify --root SYNTHETIC_RECEIVED_SCOPE --manifest EXTERNAL_MANIFEST.json --participant 000001 --session-id THE_SAME_UUID
```

`SYNTHETIC_SELECTION` must contain invented files with stable final names. The manifest must be **outside** that directory; the `session_id` must be a real canonical UUID for the same synthetic test identity. The [user guide](docs/product/GETTING_STARTED.md) gives a complete runnable example using files produced by the synthetic demo.

## Actual implementation and validation status

The following is **as verified for commit `a21279d6c7313d65eb1239e70f1bae3ae62b1420`**, not a claim about unreviewed future commits.

| Capability | Evidence / status |
|---|---|
| Recursive file discovery and conservative mother/child, session and game classification | Implemented and tested with synthetic fixtures |
| Unique unnumbered pair → inferred game 1, only with explicitly reviewed session | Implemented behind a review gate |
| Delivery contract `rg2019.delivery.v2`: independent session UUID, all selected files/auxiliaries, SHA-256 and exclusions | Implemented and tested synthetically |
| Existing offset estimator: 8 kHz audio, coarse windows ±120 s, NCC/peak/consensus tests, fine correction | Implemented, works with generated fixture audio |
| Global wide-offset FFT as a *candidate* stage | **Implemented experimentally in [draft PR #9](https://github.com/chlmz/research-video-sync/pull/9), SHA `5cbd7ddad928d36b774476f0a34e28317fff5bc4`; opt-in, disabled by default, and **not included in the pinned quickstart SHA**. Synthetic [CI](https://github.com/chlmz/research-video-sync/actions/runs/41161224041): 309 PASS Windows, 308 PASS / 1 SKIP Ubuntu; no real-media validation. |
| Isolated local synthetic processing, two MP4s, immutable results and recovery | Implemented; real execution blocked |
| Side-by-side encoding | Existing API, **not integrated into safe end-to-end flow** |
| Live field source admission, automatic NAS publication, daily scheduler | **Not authorized/implemented as a safe production path** |
| Real recording scientific alignment | **Not yet validated**; first controlled pair returned 0/7 confident coarse windows |
| Human scientific QC and release authorization | **NotApproved / pending** |
| Windows/Ubuntu CI at this SHA | [Actions run 41157402895](https://github.com/chlmz/research-video-sync/actions/runs/41157402895): Windows **296 passed**, Ubuntu **295 passed / 1 Windows-specific skip**; no failures. **Synthetic only** |

An actual pair from the cohort was inspected under private controls, with original/copy hashes preserved and visible video reportedly playable. The old estimator returned no confidence and appropriately refused to generate a synchronized result. The new optional FFT mode has **not** yet been run on the private diagnostic audio, so this status is unchanged. **Do not treat this as evidence that the data are invalid, or quietly force an offset.** The developer journal keeps the error history so it cannot be forgotten.

### Experimental wide-range FFT change (separate draft PR)

[PR #9](https://github.com/chlmz/research-video-sync/pull/9) includes an opt-in normalized full-audio candidate search and independent window validation, correcting sign/index behavior of highly asymmetric recordings. It is disabled by default. [Technical explanation](https://github.com/chlmz/research-video-sync/blob/5cbd7ddad928d36b774476f0a34e28317fff5bc4/docs/GLOBAL_FFT.md) and [exact CI](https://github.com/chlmz/research-video-sync/actions/runs/41161224041) are available at SHA `5cbd7ddad928d36b774476f0a34e28317fff5bc4`. **This code is not present in the older pinned quickstart and is not released or scientifically validated.** A hypothetical combined audio duration of ~600 seconds at 8 kHz requires approximately 1,172 MiB of *estimated additional FFT workspace*; the 512 MiB default will block. It is not a strict OS memory cap. Operators must measure actual local PCM duration/free RAM before choosing a reviewed experimental budget; no automatic increase or bypass is justified.

## Repository map

```text
pipeline_rg2019.py                 historical Python CLI (legacy live move semantics)
rg2019/syncest.py                  current windowed audio estimator
rg2019/media.py                    FFmpeg/FFprobe/audio/encode/side-by-side helpers
rg2019/discovery.py                conservative participant/session/game inventory
rg2019/delivery_v2.py              v2 selected-file receipt contract and CLI
rg2019/preproduction.py            guarded synthetic preproduction API/CLI
rg2019/storage.py                  bounded copy, attempt and committed-result primitives
rg2019/synthetic_worker.py         two-output synthetic scientific worker
examples/preproduction_demo.py     complete local generated-fixture demonstration
examples/synthetic_demo.py         earlier isolated publication/recovery demonstration
tests/                             generated-media regressions; no cohort media
docs/product/                      human guide, scientific method, AI instructions and release gate
docs/VIDEO_SYNC_ENGINEERING_JOURNAL_WIP.md
                                    decision history and known failures
sync_research_project.sh            September historical script — DO NOT DEPLOY
sync_videos.sh                      September historical script — DO NOT DEPLOY
```

September's `sync_research_project.sh` successfully demonstrated full-audio FFT offset-search behavior on controlled test signals and was reported useful for earlier pilots, but also had unguarded global maxima, batch bugs and no scientific QC. `sync_videos.sh` had the **wrong-camera trim** error. Their existence in the repository is for provenance and regression testing. See [the audited errors](docs/LEGACY_AUDIT.md) and [historical README](https://github.com/chlmz/research-video-sync/blob/a21279d6c7313d65eb1239e70f1bae3ae62b1420/README.md); neither is a current deployment recommendation.

## Sharing and privacy

Public code, scientific methods and **synthetic fixtures** are encouraged; raw or derived human-participant media, real IDs/linkage keys, identifying logs and internal infrastructure information are **not**. A public-facing architecture abstraction and the **private** full operations/identity/NAS README are intentionally separate.

Read the mandatory [public/private policy](docs/product/PUBLIC_PRIVATE_POLICY.md). Do not open a public issue or PR with real recordings, actual participant paths, server accounts, IP addresses, credential dumps or raw diagnostic logs. `.gitignore` is not protection against mistakenly pasted text or historical commits.

## Citation, licensing and product release

This repository is intended to become a citable technical/scientific software product of the Rio Grande 2019 cohort. **The reviewed tree does not yet include an approved LICENSE, `CITATION.cff`, a tagged scientific release or a DOI.** Public visibility does not itself grant unrestricted reuse permission. Institutional authorship, software licensing, credits and release metadata require approval before claiming an official open-source release.

See [release checklist and technical-product reporting fields](docs/product/RELEASE_CHECKLIST.md). The documentation will be finalized only after synthetic tests, controlled real-media alignment, independent QC, output publication and operational security gates are satisfied. **This public README is a review draft, not the final product citation.**

## Maintenance principles

- Pin exact commits or release tags when validating claims.
- Distinguish code/CI evidence, operator report, manual scientific observation and hypothesis.
- Preserve failed approaches and why they failed, rather than rewriting history.
- Test changes against synthetic data first, and keep ingestion, technical success and scientific QC separate.
- Publish only sanitized documentation. Keep exact network configuration and the operations manual privately, **without embedded secrets**.

For an AI implementing an equivalent workflow in another cohort, start with the **[AI adaptation guide](docs/product/AI_ADAPTATION_GUIDE.md)** rather than trying to infer behavior from filenames or the September shell scripts.
