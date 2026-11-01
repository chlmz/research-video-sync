# GPIS — Conceptual research-video workflow (public architecture draft)

> **Status (2026-11-01):** logical design and evidence levels only. NOT a network diagram, equipment inventory, deployed configuration or production attestation.
>
> The complete infrastructure and access documentation is **private**. Never paste real asset identities, physical locations, hostnames, IPs, storage mounts, ACLs, credentials, task details, backup arrangements, logs or research-media metadata here.

## Public conceptual topology

```text
Camera acquisition
       |
Controlled transfer -> ARRIVAL (logical INBOX)
       |
Complete receipt evidence + reviewed session/game identity
       |
       v
Immutable originals (logical RAW) [future operational integration]
       |
       v
Authorized local scratch -> September audio FFT -> three MP4 candidates
                                              |
                                    QC = NotApproved
       |
       v
Verified technical output store (logical SYNCED) [future authorization]
       |
       v
Separate scientific QC and downstream analysis
```

The labels `00_INBOX`, `01_RAW` and `02_SYNCED` name **workflow concepts**, not literal disclosed directory paths or claims of deployed working shares. Technically verified MP4s can in principle be archived with scientific QC pending, but only following separate operational authorization. Scientific approval controls downstream analysis and use.

## Responsibilities — abstract design, not actual accounts or ACLs

| Function | Intended boundary | Evidence status |
|---|---|---|
| Acquisition and delivery | Preserve sources and close a verifiable receipt | Real field-producer integration pending |
| Original archive | Copy all declared original bytes, verify integrity, never delete input | Real RAW admission not validated |
| Local scientific worker | Read only authorized originals; calculate candidate lag; create MP4s without altering originals | Local adapter exists; unattended processing not validated |
| Derived output archive | Integrity-checked non-overwriting technical publication | Real SYNCED publishing not validated |
| Scientific QC | Separate, documented human decision about actual synchronization | One visual pilot PASS reported, formal multi-point QC pending |

## What is verified and what is not

- **[CODE / SYNTHETIC]** Draft [PR #4](https://github.com/chlmz/research-video-sync/pull/4), [#5](https://github.com/chlmz/research-video-sync/pull/5), [#6](https://github.com/chlmz/research-video-sync/pull/6) and [#7](https://github.com/chlmz/research-video-sync/pull/7) describe conservative discovery, generated-fixture processing, recovery and reception contracts. Their test results do not establish a working real pipeline.
- **[CODE / SYNTHETIC REPORT]** The [September field adapter, draft PR #10](https://github.com/chlmz/research-video-sync/pull/10) contains the method fixed at `0a143d33862a274e3e9c8ed25495121218a9acac` with 12 locally reported focused synthetic tests. Its outputs are **local QC candidates**; it does not admit originals to RAW or publish to SYNCED.
- **[FIELD REPORT]** One controlled real-media execution reportedly produced three local MP4 candidates and preserved source-copy integrity.
- **[MANUAL / USER REPORT]** The investigator later reported visually perfect synchronization. The case-level beginning/middle/end record, quantitative tolerance and formal scientific QC disposition are still missing.
- **[OPEN]** Verified field completion/manifest, immutable RAW admission, operational publication, integrity/durability/recovery, permissions, unattended scheduling and formal scientific QC remain separate tasks. No synthetic CI or visual playback can automatically satisfy them.

## Separation from operational records

This document intentionally excludes exact hardware inventory, site/location, network and remote-access design, user/service accounts, permissions, backups, maintenance or scheduling. Keep that information solely in an authorized **private** document, without passwords, tokens or recovery keys. Consult the [scientific method](product/SCIENTIFIC_METHOD.md), [synthetic-only guide](product/GETTING_STARTED.md), [engineering history](VIDEO_SYNC_ENGINEERING_JOURNAL_WIP.md), [privacy rules](product/PUBLIC_PRIVATE_POLICY.md) and [release checklist](product/RELEASE_CHECKLIST.md) for distinct public-scoped information.
