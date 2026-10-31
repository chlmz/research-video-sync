# GPIS — Infrastructure and video workflow architecture (public-safe draft)

> **Status:** Working draft, 2026-10-30. Not an operational runbook, penetration-test map, or production attestation.
>
> **Security:** This repository is public. This document intentionally excludes internal IP addresses, Tailscale identities, machine/account logins, firewall rules, credential-handling procedures, backup paths and private administrative details. The definitive **private** operational README must be maintained outside this public repository.

## Why this document exists

The GPIS video synchronization workflow is a distributed research data system. It must make the path of every original file traceable, keep research data immutable after admission, process only authorized sessions and publish verifiable derived results. The network and identity architecture must be documented separately from the scientific algorithm. Another AI should be able to distinguish **computer infrastructure**, **research data workflow**, **scientific execution**, and **QC authorization**.

The final documentation is split into three products:

1. **Scientific/technical pipeline README (final, pending):** exact algorithms, parameter rationale, actual behavior, inputs/outputs by session/game, QC and confidence rules, acceptance tests, edge cases, troubleshooting, deployment, reproducibility and adaptation to other studies.
2. **Private infrastructure and access README (final, pending):** actual machines, operating systems, accounts and trust boundaries, IP/addressing and remote access, SMB/Drive mounts, exact ACLs, scheduled tasks, backups, UPS, failure recovery, maintenance and incident procedures. **Never put it in a public repository.**
3. **Engineering history/lessons-learned:** `docs/VIDEO_SYNC_ENGINEERING_JOURNAL_WIP.md` — chronological account of what was attempted, what passed, errors, hypotheses, code SHAs and decisions; preserve it independently of the eventual clean final runbook.

## Conceptual topology (public-safe)

```text
Research field capture cameras
           |
           v
Field workstation — camera copy and local selection
           |
       Synology Drive
           |
           v
Research NAS — 00_INBOX (arrival)
           |
       receipt integrity + human session/game review
           |
           v
Research NAS — 01_RAW (admitted immutable originals, future)
           |
      authorized read-only input
           |
           v
Dedicated 24/7 Windows analysis server — local scratch / FFmpeg / QC
           |
       staged, verified derived outputs
           |
           v
Research NAS — 02_SYNCED + 99_LOGS_QC (future authorized publication)
           |
           v
Downstream analysis, FaceReader, and scientific review
```

Remote administration traverses an authenticated private overlay network; it is **not** an exposure of SMB to the public internet. Field transfer and remote administration are different channels. The experimental code runs under a least-privilege service identity, not an administrator.

## Known architecture (descriptive, no sensitive identifiers)

- **Home research site:** Internet router, managed multi-gigabit Ethernet switch, dedicated Windows server and a Synology 4-bay NAS. Both server and NAS are attached to the switch. Current server Ethernet operates at 1 GbE; upgrading to 2.5 GbE is a *plan*, not a completed fact.
- **Server:** Windows 11, Intel multicore CPU, locally installed Python 3.12 and FFmpeg/FFprobe, a scratch workspace, persistent remote maintenance and automatic health/configuration monitoring. Scientific processing is **disabled pending authorization**.
- **Storage:** Synology DSM, shared research datasets, redundant disk pool (not a backup), and a separate auxiliary namespace for synthetic acceptance tests. Synology Drive is used for data delivery from the field computer. Exact permissions still require review before production.
- **Field site:** one Windows computer controls camera ingest and Synology Drive transfers; two external drives have been described as backup targets, but backup scope, last run and restore evidence still require verification.
- **Power protection:** a sine-wave UPS is reported for the server. Whether USB signaling, shutdown automation, and the NAS/switch are protected remains to be verified.
- **Remote access:** private overlay network and remote desktop application. Preserve least privilege and do not publish internal network identifiers or access secrets.

## Storage namespaces, as designed (not all operational)

```text
FOLLOWUP_2026/
  00_INBOX/             # field arrival; never presume transfer complete from quietness
  01_RAW/               # intended immutable admitted originals
  02_SYNCED/            # scientifically authorized derived videos, not yet live
  03_WORKSPACE/          # reserved project workspace, not server-local scratch
  04_FACEREADER_OUTPUT/  # FaceReader outputs, outside current sync pipeline
  05_ANALYTIC_DATA/      # analytical data, outside current sync pipeline
  99_LOGS_QC/            # trace, manifests and review records
PILOTS/
  00_SOURCE_LEGACY/      # preserved historical reference, immutable
```

Do not assume each directory is ready for production merely because it exists. Do not move 00_INBOX → 01_RAW with the legacy script. Only a verified final delivery manifest and an independently reviewed session/game can authorize the *next* stage; reception success is separate from scientific QC.

## Roles and trust boundaries (abstract)

| Role | Intended capabilities | Prohibited / not yet authorized |
|---|---|---|
| Field delivery identity | Upload selected source material to dedicated arrival namespace | Delete/mutate admitted RAW, modify analysis outputs |
| Server service process | Read verified approved inputs, local scratch processing, limited publication of derived data after explicit approval | NAS administration; move/delete originals |
| NAS service identity | SMB operations limited to specified approved shares and paths | Global dataset write access, DSM administration |
| DSM administrator | Scoped storage management and authorized ACL changes | Routine processing of scientific data under administrative identity |
| Research reviewer | Confirm session/game mapping and scientific QC | Treat machine-completed encoding as scientific approval |

**Note:** current actual ACLs must be inspected. This table is a target separation of duties, **not evidence** that those permissions are already implemented.

## Verified milestones and known gaps

- Local service account execution and auxiliary SMB filesystem behavior were tested successfully on the dedicated server with synthetic data; historical NAS access logs corroborate the service-related NAS user in an earlier run. No claim is made here that an independent NAS login observation was captured for every later run.
- The repository tests on Linux/Windows validate synthetic scenarios, not live production data and not scientific alignment of actual mother-child recordings.
- The first real pair remained blocked scientifically after audio correlation failed to find consensus; original files were not modified. The researcher reports the videos play normally. Distinguish incidental AVI/H.264 warnings from demonstrable unrecoverable corruption.
- **Open:** actual field PC copy tool integration; persistent scientific session UUID; verified transfer completion; final ACL matrix; durable RAW ingestion; output publishing to scientific shares; live full-length resource limits; scheduled jobs; scientific QC tolerances; backup/restore drills; UPS shutdown; security review.
- **Open:** explicit ownership of each administrator/service/field role, credential rotation and on-call responsibilities, documented only in the private runbook.

## Release and update policy

- Update this **public-safe** architecture document whenever design changes, but never paste internal access details here.
- Maintain the private network inventory separately, with exact paths, hostnames, IPs and access controls, **but no passwords, recovery keys, session tokens, or other secrets**.
- The final pipeline and network READMEs must contain an evidence matrix and distinguish *as designed*, *as observed*, *last verified*, and *pending*.
- Do **not** label the project production-ready until a real, scientifically reviewed sample has passed and operations/permissions have been explicitly authorized.
