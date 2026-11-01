# AI agent guide — understand, reproduce and adapt RG2019 video synchronization

> **Authoritative final algorithm specification:** [September 2026 full-audio FFT algorithm](https://github.com/chlmz/research-video-sync/blob/codex/gpis-september-field-adapter/README_VIDEO_SYNC_ALGORITHM_FINAL.md). Preserve this fixed reference when reproducing the successful pilot. This guide additionally covers the *separate* operational/synthetic architecture; the NAS pipeline remains private and incomplete.

> **Purpose:** a deterministic, evidence-first handoff protocol for any coding or research AI. This is **not** a system prompt granting access to real research files, accounts or networks. The repository and this guide are public. Reference implementation reviewed at `a21279d6c7313d65eb1239e70f1bae3ae62b1420`. Some major features remain restricted to synthetic data.

## Start here (mandatory reading order)

1. Read root [README.md](../../README.md) for the exact **current release/readiness status**.
2. Read [GETTING_STARTED.md](GETTING_STARTED.md) and run synthetic tests before proposing modifications.
3. Read [SCIENTIFIC_METHOD.md](SCIENTIFIC_METHOD.md) and the executable implementations `rg2019/syncest.py`, `rg2019/media.py`, `rg2019/synthetic_worker.py`.
4. Read `docs/DELIVERY_V2.md` and code `rg2019/delivery_v2.py` / `rg2019/discovery.py` to understand session, game, receipt, integrity and QC.
5. Read `docs/PREPRODUCTION.md`, `docs/STORAGE_PERMISSIONS.md`, `rg2019/preproduction.py`, `rg2019/storage.py` and `rg2019/fs_errors.py` before touching execution or publication.
6. Read `docs/LEGACY_AUDIT.md` and regression tests before proposing any reuse of the September shell scripts.
7. Read `docs/VIDEO_SYNC_ENGINEERING_JOURNAL_WIP.md` to understand historical bugs and known dead ends.
8. Read [PUBLIC_PRIVATE_POLICY.md](PUBLIC_PRIVATE_POLICY.md) before creating prompts, data, logs, diffs or public docs.

**Never infer implementation from a design document alone.** For every important claim, pin the **exact current commit SHA**, inspect the actual function and identify its tests. Look at the full PR/CI for the same SHA. The default `main` may lag stacked draft PRs. Check the branch and merge status; a draft PR is not a released version.

## Five independent state dimensions

A correct system must not collapse these into one green "success":

1. **Discovery**: correct participant, independently identified session, one unambiguous mother/child pair per game.
2. **Receipt**: declared complete selection and exact received set, including relevant auxiliary files.
3. **Integrity**: sizes, SHA-256, unchanged sources, provenance, duplicates/collisions handled.
4. **Technical media processing**: audio extraction, supported offset, correct cut, usable MP4, intact publication and recovery.
5. **Scientific QC + production authorization**: independent reviewer and explicit acceptance criteria; never inferred from exit code, receipt or published file.

The final pipeline must account for all five. At reference SHA, the newer safe processing path is **synthetic-only**.

## Non-negotiable scientific invariants

- Temporal offset sign: `offset_seconds = t_mom - t_child`; positive => **trim mother**, negative => **trim child**. Keep regression tests for both signs and zero.
- Never equate `duration(mother) - duration(child)` with the start offset.
- Never infer a game from `SNAP` sequence, camera A/B, sorted filename, date proximity or directory iteration order.
- Unique unnumbered pair → game 1 only within a separately delimited, explicitly reviewed session, and record `game_origin=inferred_unique_pair`.
- Multiple games require explicit matching numbers or review.
- Preserve all source bytes. Never mutate/readmit originals by treating a copy completion flag as scientific receipt.
- Manifest `rg2019.delivery.v2`: separate independent session UUID and delivery identity; exact selected paths, size and hash; sidecar outside its own declared scope; explicitly documented exclusions. A UUIDv5 integrity identifier **is not a sender signature**.
- `ReceptionVerified` does **not** imply `QCApproved`.
- Do not equate an unqualified FFT peak with a **scientifically approved** offset. The selected [September adapter (draft PR #10)](https://github.com/chlmz/research-video-sync/pull/10) intentionally uses the historical full-audio NumPy FFT maximum **to generate local candidates for visual QC**, not automatic approval. The alternative gated FFT/NCC design in [draft PR #9](https://github.com/chlmz/research-video-sync/pull/9) remains experimental and **is not a prerequisite**. Do not reinstate mandatory claps/manual acoustic anchors or repeated NCC threshold tuning. Synthetic CI alone cannot validate field synchrony.
- Do not change or bypass thresholds merely to make a difficult sample pass.
- Do not silently transform an AVI into MP4 by renaming it; use measured media information to decide on remux/transcoding.
- No automatic scheduling or live NAS publication until explicit operational + scientific acceptance.

## Engineering invariants

- Every job identified by participant/session/game **and input fingerprint**, with committed parameters.
- Read-only original input; scratch is on a dedicated local disk and has bounded capacity.
- No overwrite or silent cleanup of unknown files, interrupted attempts or prior outputs.
- Published result is valid only when re-reading the expected manifest and committed marker; the mere presence of MP4 is insufficient.
- Retry only defined transient conditions; do not turn access denial, path-length, unknown state or hash mismatch into "network timeout".
- Windows compatibility includes standard path budgets, permissions, open handles and process-tree termination, not merely passing Linux CI.
- Keep infrastructure private; GitHub public. Tests use invented identifiers and generated synthetic media.
- Preserve historical scripts as cautionary references; do not run them on current scientific folders.

## Reproducibility contract for each change

Report all of the following, or say what could not be verified:

| Field | Required evidence |
|---|---|
| Baseline | repo URL, base SHA, branch, PR |
| Change | precise code paths/functions and behavior before/after |
| Math | sign convention, candidate search, normalization, confidence/false-positive controls |
| Inputs | entirely synthetic fixtures; no real participant data in public tools |
| Tests | exact command, OS/Python/FFmpeg versions, collected/pass/fail/skip and skip reason |
| Performance | synthetic resource profile at defined input size, not extrapolated to all field videos |
| Integrity | SHA and immutable source assertions |
| Security | permissions, path/UNC guard, no secrets, no public logs |
| Scientific QC | NotApproved until independently authorized |
| Deployment | not performed unless explicitly approved |
| Remaining limitations | named, non-obscured blockers |

Do not claim "validated on Synology" from GitHub Actions or "synchronized real videos" from synthetic fixtures. A prior operational report may be useful evidence but is not a substitute for current field verification.

## Adaptation checklist for another research project

Before writing code, obtain (or explicitly mark unknown):

| Domain | Questions |
|---|---|
| Research unit | What is a participant? Are there visits, sessions, games and sub-recordings? Which are independent? |
| Pairing | Which camera roles exist? Could multiple cameras use the same naming scheme? How are candidates reviewed? |
| Source formats | Which containers, codecs, audio streams, fps, VFR/timestamp issues and typical lengths occur? |
| Temporal model | Constant lag or drift? Expected time offset? Is audio shared? Are claps/other anchors available? |
| Sender workflow | How are files copied, renamed, checked, closed, transported and retried? What is the final manifest? |
| Privacy | What is consented to? Where may raw audio/video be processed? Which fields must never appear in public logs? |
| Infrastructure | What OS, CPU/storage, backup, transport, ACL and network trust boundaries apply? (answer privately) |
| Output/QC | Desired files, timebase, manual review scheme, offset/drift tolerance, ownership, rejection policy |
| Recovery | What must survive crashes, partial uploads, re-runs and simultaneous writers? |
| Publication | License, attribution, DOI/citation, versioning, scientific evidence and institutional permission |

Do not insert guessed answers into source code; use explicit options, unknown states, or blocked configurations.

## Reference prompt for a future AI

> You are implementing or adapting an open scientific video synchronization tool. Start by reading the repository's README, product guides, scientific estimator implementation, legacy audit and tests at a pinned SHA. Establish each research unit (participant/session/game), the exact audio offset convention, manifest/provenance requirements, source immutability and independent scientific QC. Use only invented test data in public/cloud environments. Propose a bounded plan and a smallest safe proof on synthetic files. Never deploy a live ingestion path or alter real data without separate authorization. Make mathematical changes behind regression tests for offset signs, large lags, unrelated audio, inconsistent durations and drift. Explain every evidence gap rather than assuming success. Follow the repository's public/private policy and report exact CI evidence and unvalidated constraints.

## Suggested delivery structure for an AI implementation task

1. Verified baseline and scope.
2. Scientific hypothesis and invariant checks.
3. Minimal code change and migration/compatibility consequences.
4. Synthetic tests and CI.
5. Failure modes, privacy/security audit and operational limits.
6. Decision: `PASS synthetic`, `BLOCKED real scientific` or `PASS real scientific` with **actual independent evidence**.
7. Proposed next step that does not repeat already completed checks.

## Failure-history quick index

- September `sync_videos.sh`: inverted trimming camera for nonzero offsets.
- September `sync_research_project.sh`: whole-audio FFT covers large lags, but its unvalidated global maximum and unsafe Bash/fallback must not be reinstated. PR #9 implements corrected overlap-normalized lag candidates with bounded-memory admission, still without empirical field QC.
- Historical copy JSON: successful local copy does not prove Synology Drive delivery; size coincidence cannot prove identity.
- Original Python live script: can move INBOX to RAW, incompatible with newer deep session trees and safe non-destructive preproduction.
- Original Windows long paths: required compact v2 result layout and explicit path preflight.
- Real pilot October: the earlier windowed/NCC route failed its confidence gates. Later the September adapter reportedly exported three local MP4s successfully, and the investigator reported visually perfect synchronization. Preserve both historically, but do not infer formal multi-point QC or NAS publication.
- Safe synthetic preproduction: deliberately blocked from real media, not proof of production deployment.

## Change-management rule for this guide

Update only for **new verified evidence**. Preserve earlier failed approaches and rationale in the engineering journal. A final independent product release should include a pinned tag and versioned, self-consistent docs, not moving drafts.

Related documents: [scientific method](SCIENTIFIC_METHOD.md), [human quickstart](GETTING_STARTED.md), [public/private policy](PUBLIC_PRIVATE_POLICY.md), [release gate](RELEASE_CHECKLIST.md).
