# Public scientific software product — release and reporting checklist

> **Status at 2026-10-30:** PRE-RELEASE / research prototype. The public GitHub repository exists, but its main branch and draft PRs do not constitute an operationally or scientifically validated release. This document is a gate, **not a declaration of completion**.

## Intended product identification (draft)

| Metadata | Current value / required action |
|---|---|
| Working English title | RG2019 Research Video Synchronization Pipeline |
| Affiliation with research | Coorte de Nascimentos de Rio Grande 2019; research video processing workflow |
| Type | Scientific research software / reusable technical product |
| Public source repository | https://github.com/chlmz/research-video-sync |
| Supported modality | Dual audiovisual recordings of mother-child interactions, with generalizable roles |
| Core method | Audio-derived constant offset, validation, frame-accurate trim/MP4 encoding, guarded publication |
| Repository version for reviewed contract v2 | `a21279d6c7313d65eb1239e70f1bae3ae62b1420` (draft PR #7; **not** a release) |
| Project maintainer(s) and author contributions | **To be approved**; do not invent names or contributor order |
| Institution(s), acknowledgments and funding | **To be confirmed** through official records |
| License | **Not specified** in the reviewed tree; choose and add an approved open-source license before inviting reuse |
| Release tag/version | **Not assigned** |
| Archived DOI / permanent software citation | **Not assigned**; prepare after approved release |
| Citation file `CITATION.cff` | **Not yet published**; write from approved contributor and release metadata |
| Ethics and data sharing | Human participants' media and identifying records remain nonpublic; ethical review and permissions must be verified by project leadership |
| Validation statement | Windows/Ubuntu synthetic CI only; initial real pair failed confidence gate; no accepted field sync output yet |

Do not describe this product as validated, certified, clinically appropriate or production-ready until the checkboxes below are supported by evidence.

## Gate A — methods and implementation

- [x] Original algorithm/sign convention and legacy defects have reproducible references.
- [x] Separate scientific method, human quickstart, AI adaptation guide and public/private boundary are drafted.
- [x] Guarded synthetic workflow, deep discovery and versioned delivery contract exist in draft source branches.
- [ ] Decide how to implement/test wide-lag offset candidate generation and independent multiclip confirmation without excessive memory.
- [ ] Validate full-length field AVI/H.264/PCM behavior and timestamp consistency; distinguish harmless warnings from actual frame corruption.
- [ ] Integrate scientifically reviewed session/game identity and final producer manifest with the field copy workflow.
- [ ] Integrate side-by-side generation with the **safe** processing executor, if adopted as mandatory final output.
- [ ] Define durable output filenames and destinations keyed by participant/session/game; prevent collision across visits.
- [ ] Establish operational resource budgets for full-duration media (disk, temp, memory, CPU, cleanup and retry policy).
- [ ] Version/lock reproducible dependencies and supported FFmpeg combinations; do not assert all upstream versions work.

## Gate B — independent scientific validation

- [ ] Obtain a correct, reproducible offset on a real authorized paired recording, not merely a synthetically generated test.
- [ ] Validate at least beginning/middle/end of overlap against recognizable events with documented scientific tolerance.
- [ ] Evaluate drift and recurrent failures in recordings with unequal durations, weak audio, multiple games and different capture setups.
- [ ] Define acceptance thresholds *before* classification, including where manual adjudication is required.
- [ ] Demonstrate that wrong pairs and unrelated audio are rejected.
- [ ] Produce MP4 and (when required) side-by-side with verified decodability, correct trims and scientifically approved alignment.
- [ ] Record human reviewer authority, date, reproducible algorithm/config version and disposition for each assessed case.
- [ ] Document a representative real-media validation series privately, and publish only ethically permissible aggregate metrics.

## Gate C — operational and security readiness

- [x] The safe synthetic pipeline is designed to remain disabled for real data.
- [x] The source repo avoids placing raw participant media in GitHub and has a restrictive `.gitignore`.
- [ ] Approve least-privilege service accounts and ACLs for field arrival, admitted RAW, publish and QC.
- [ ] Validate immutable RAW ingestion from a finalized delivery without deleting or moving sources prematurely.
- [ ] Verify field workstation tool and Synology Drive behavior through a fully synthetic end-to-end delivery.
- [ ] Verify correct output publication and independent COMMITTED/manifest readback, including recovery, concurrent writers and idempotence.
- [ ] Validate real full-length load and capacity; retain backup/restoration and incident response procedures in **private** runbook.
- [ ] Explicitly authorize any real-processing task/schedule. Draft code must not self-enable live mode.
- [ ] Review the public Git history, tracked files, CI logs and all release attachments for personal or infrastructure identifiers.

## Gate D — public software release and discoverability

- [ ] Review the public root README for congruence with actual code/tag and correct entrypoints.
- [ ] Add approved software license (current absence means public visibility does **not** imply permission for unrestricted reuse).
- [ ] Confirm maintainers and authors, affiliations and acknowledgement wording with the research team.
- [ ] Create `CITATION.cff` and project-recommended citation with version, repository, date and permanent identifier if available.
- [ ] Tag an immutable reviewed release (e.g. semantic versioning after scope is approved); do not invent a release number.
- [ ] Archive release in an approved research-software repository, such as an institutional repository or a DOI-capable service, if consistent with the project's publication plan.
- [ ] Attach reproducible synthetic example, independent QC/test matrix, supported-platform versions, security boundary and limitations.
- [ ] Link technical product record to the cohort's approved project outputs and report the correct version/DOI.
- [ ] Set owner, maintenance policy, issue support policy and changelog; avoid public bug reports containing real recordings or logs.
- [ ] Archive public user instructions and private operations manual as **separate** versioned artifacts.

## Suggested evidence package for reporting as a research technical product

When evidence exists and team attribution is approved, report:

1. **Product identity:** exact name, institutional context, version/tag, link and persistent citation.
2. **Function:** robust, reproducible alignment and protected derivation of dual-camera audiovisual data for research; avoid conflating automatic alignment with scientific approval.
3. **Novelty/design choices:** conservative session/game discovery, explicit delivery manifests, windowed/validated sync, provenance, recovery-safe publication and separation of QC states. Do not claim scientific novelty unless independently justified.
4. **Reproducibility:** documentation, generated fixtures, CI evidence, parameters, deterministic tests, license and user/AI runbooks.
5. **Validation:** aggregate scientific accuracy/failed cases, manual audit design and technical reliability. Document which metrics were synthetically versus empirically demonstrated.
6. **Research impact and use:** publications, cohorts, training, reuse and software adoption **only if verified**, without disclosing participant data.
7. **Responsible team:** approved authors, affiliations, funding acknowledgements and maintenance/contact role.

No claimed publications, funding, impact numbers, DOI, licensing terms or contributors should be invented.

## Versioning and finalization workflow

1. Keep historical journal intact for the narrative of failures and rationale.
2. Evolve root README, human guide, scientific methods, AI guide and release gate on a documentation review branch as code develops.
3. When a scientific release truly passes Gates A–D, replace tentative wording with final tested commands and outputs, pin an immutable SHA and tag, finalize citation/license, and publish a human-readable release note.
4. Produce a **separate private** full README for actual network/users/NAS/computers and authorized operations. Never copy that private README to public GitHub.
5. Approvals and merges are distinct: drafting this checklist does not perform them.

References: [home](../../README.md), [methods](SCIENTIFIC_METHOD.md), [synthetic user guide](GETTING_STARTED.md), [AI reuse](AI_ADAPTATION_GUIDE.md), [privacy rule](PUBLIC_PRIVATE_POLICY.md), and [engineering history](../VIDEO_SYNC_ENGINEERING_JOURNAL_WIP.md).
