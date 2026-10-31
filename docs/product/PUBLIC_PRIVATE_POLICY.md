# Public/private separation policy — mandatory for this repository

> **Project rule:** This repository is public. Public software artifacts must be reproducible **without** disclosing research participants, their media, internal network topology, access configuration or credentials. Private infrastructure documentation belongs in access-controlled storage outside GitHub.

## What may be published

| Category | Public example | Condition |
|---|---|---|
| Scientific methods | Offset definition, FFT/NCC equations, QC decision logic | Correctly reviewed; no participant-specific data |
| Code | Generic Python modules, CLI, deterministic tests | Reviewed for embedded tokens, fixed paths, credentials, real IDs |
| Synthetic examples | Generated audio/video with invented participants and UUIDs | No sourced or recombined real recordings |
| Deployment design | Abstract "field workstation → NAS → analysis server" topology | No real addresses or access mechanisms |
| Tests and performance | Aggregate CI counts, invented-fixture benchmarks | Identify platform/commit; do not claim real scientific QC |
| Documentation | User guide, AI handoff, change log, public architecture, release notes | No logs/screenshots from real participants or servers |
| Scientific product record | Approved maintainers, institutional credits, published paper/DOI and software version | Verify attribution and approvals before release |

A document being Markdown, a repository being public already, or a file being excluded by `.gitignore` does **not** make its contents automatically safe.

## What must remain private

- Every research subject's raw or derived video, audio, face, voice, media screenshot, real participant identifier, study linkage key, time/place of private recording and source-specific hash.
- Actual server/NAS/computer host identifiers, local and overlay IP addresses, exact drive/share/mount paths, internal URLs, account list, account privileges, ACL dumps, firewall rules, task scheduler XML, recovery procedures that reveal internal authentication, logs with filesystem or login details.
- Passwords, authentication tokens, private SSH keys, recovery keys, personal email accounts, network credentials and any cryptographic secrets **must never appear even in the private README**. Store secrets only in the approved secret management system, and refer to a retrieval procedure without embedding values.
- Database exports, research datasets, operational diagnostic files containing internal paths, user profiles, scripts with hard-coded accounts, files supplied by private collaborators.
- Public fragments that could identify a subject indirectly even after the name was removed (timestamps, file sizes, filenames, location or unusual combinations).

Some hardware descriptions may be non-sensitive, but the full topology, access routes and security posture are operationally sensitive. Keep those specifics in private inventory.

## Storage strategy

**Public GitHub:** `README.md`, `docs/product/*`, scientific source code, synthetic test generators, `docs/VIDEO_SYNC_ENGINEERING_JOURNAL_WIP.md` (sanitized), `docs/GPIS_INFRASTRUCTURE_ARCHITECTURE_WIP.md` (high-level sanitized).

**Private controlled storage:** `README_GPIS_INFRASTRUCTURE_PRIVATE_FINAL.md` and its living working draft, actual IP/host/user and ACL inventories, secrets references, backup restoration manuals and hardware maintenance records. Do **not** put an encrypted private runbook in the public repo unless explicitly authorized and reviewed; ciphertext, history and metadata create risks too.

**Scientific evidence storage:** original and processed human-participant media, real QC tables, logs and operational manifests, under the approved research data governance/access controls — never in this public repository or a public issue attachment.

## Safe publication workflow

1. Choose destination as **public** or **private** before drafting. Prefer public-safe neutral examples in generic docs.
2. Use obviously invented identities (`000001`, `000002`), hypothetical sample fixtures and fictitious local sandbox paths. Do not paste pseudonymized real identifiers if they could be linked to participants.
3. Review the *entire diff, commit message, filenames, branch name and attachments* for secrets, actual addresses, internal routes, participant identifiers, code comments and metadata. Diff-only checks are not enough for previously committed secrets.
4. Use `git status` and `git diff --check`; inspect candidate files with secret scanning and manual review. `.gitignore` is defense-in-depth, not a privacy boundary.
5. Review all documentation and CI logs generated from the change. Public Actions logs must not process or print private data.
6. Never commit a "temporary" credential or real screenshot expecting to remove it later; Git history retains it.
7. If sensitive content appears publicly, **stop publication and follow the incident/credential-rotation process in the private runbook**. Deleting a commit alone may not remove cached copies.
8. Confirm that the release's screenshots, synthetic demos, data citations and attribution also meet the cohort's ethical/data governance requirements.

## Rule for AI assistants

- No private-data access or exfiltration is implied by a public source-code task.
- Do not upload, embed, summarize verbatim or cite real internal logs in public README/issues/PRs.
- When needed for debugging, work within approved private tools and communicate **redacted high-level findings** to the public code repository.
- If a user requests a public artifact containing private details, propose a sanitized public document and a separate private document.
- Treat the absence of a credential in a public repo as a design requirement, not an invitation to derive or request it.
- The user may explicitly authorize internal documentation, but that does not authorize disclosure to GitHub.

## Final document acceptance test

A public document is ready only when a collaborator unfamiliar with the local deployment can understand and reproduce the **synthetic behavior** without learning who the study participants are, how to reach the private NAS, how users authenticate, or which security weaknesses exist in the live installation.

The corresponding private architecture README should contain enough accurate, last-verified detail for an authorized operator to restore service while containing **no actual passwords, tokens or recovery secrets**.
