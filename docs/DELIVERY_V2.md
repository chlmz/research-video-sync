# Reception contract v2 and FURG adapter boundary

Base: `21184f99628d8ba79cb5a8badc12cf6f8742c820`. This adds a read-only contract
and candidate planner, not a live scientific execution path. v1, historical logs,
StateStore and the scientific estimator are not migrated or overwritten.

## Contract

The exact top-level fields are `schema` (`rg2019.delivery.v2`),
`generator_version` (`rg2019-delivery/2.0.0`), `participant` (six-digit string),
`session_id` (independent canonical UUID), `closed_at` (ISO timestamp with offset),
`selection_closed` (true), `files`, `exclusions`, `delivery_id`.

Each file has `path` (portable relative POSIX path), `name` (current basename),
`original_name` (null or explicitly supplied previous relative name/path), `size`
(nonnegative integer), `sha256` (64 lowercase hexadecimal characters), `material`
(AVI/Auxiliary360/HistoricalJSON/Other), `role` (mom/child/null), `game` (integer/null).
Exclusions have all these fields plus a nonempty `reason`; their bytes are still
hashed/verified as evidence, but they are excluded from the declared included list.
The candidate planner remains conservative and will not silently ignore a
conflicting AVI merely because a sender excluded it.

The delivery UUID is UUIDv5(URL namespace, SHA-256 of canonical JSON of every field
except delivery_id); canonical JSON sorts keys and uses compact separators. Files
are sorted by path. Reusing identical selection, session, timestamp and trace
metadata yields identical output. Changing any evidence creates a different
delivery identity; it never replaces an older manifest. This is an integrity ID,
not a signature or authentication of the sender.

Manifest storage is **outside the selected delivery scope**. Transport it as a
sidecar, with an explicit receiver mapping to the corresponding scope. This both
prevents self hashing and avoids treating a manifest as an additional selected
file. A supplied session UUID must be independently matched by the receiver;
participant IDs, camera codes, SNAP indices and timestamps cannot provide it.

## APIs and CLI

`delivery_v2.generate(root, participant=..., session_id=..., closed_at=...,
selection_closed=True, exclusions={relative_path: reason},
originals={current_path: previous_path})` returns the document. It hashes bounded
1-MiB chunks and checks the complete path/size/mtime/inode inventory before/after.
Transfers, links/junctions, path collisions, changing/inaccessible files fail.
`save(root, external_path, document)` re-verifies, creates exclusively and permits
only an identical existing document. Torn/conflicting files remain untouched.
Filesystem checks assume a trusted, quiescent selection, not adversarial writers
restoring metadata between syscalls. There is no atomic snapshot across machines.

```text
python -m rg2019.delivery_v2 generate --root LOCAL_SELECTION --manifest EXTERNAL_JSON --participant 000001 --session-id 00000000-0000-0000-0000-000000000001 --closed-at 2026-01-01T00:00:00+00:00 --closed
python -m rg2019.delivery_v2 verify --root RECEIVED_SCOPE --manifest EXTERNAL_JSON --participant 000001 --session-id 00000000-0000-0000-0000-000000000001
```

Optional `--selection-metadata FILE` supplies exactly the `exclusions` and/or
`originals` maps. CLI returns JSON and exit 0 on generation/verified reception,
20 otherwise. Exit 0 is never scientific authorization. `verify` returns missing,
additional and mismatched paths and QC NotApproved. Read errors preserve evidence.

## States and pairing

| Observation | Reception state | Integrity | Processing/QC |
|---|---|---|---|
| Manifest arrived, scope/files absent | WaitingForDelivery | NotVerified | blocked / NotApproved |
| Hash or size differs | IntegrityError | Failed | blocked / NotApproved |
| Extra files, collision, invalid schema/identity, scan changes | NeedsReview | NotVerified | blocked / NotApproved |
| Complete exact set and hashes | ReceptionVerified | IntegrityVerified | still blocked / NotApproved |

Every verification recomputes state; no stale success survives a changed file.
Integrity errors take precedence over missing files; unresolved additional files
require review even if another file is missing. Close-of-selection does not prove
Synology Drive completion. A corrected/new delivery needs a new manifest and
explicit session association; no evidence is deleted during reconciliation.

`discover_field(..., reviewed_sessions=[configured_root])` infers game 1 only for
exactly one unnumbered mom and child, without contradictions/additional candidates.
It records `game_origin=inferred_unique_pair`; numbered pairs retain explicit
numbers. Default discovery keeps historical unspecified-game behavior.
`synthetic_plan.plan` accepts the same explicit review argument and binds the
classification to its fingerprint. `delivery_v2.reception_plan` verifies first,
then reuses that planner for the mapped session. Every returned job stays Blocked:
reception, session review, scientific authorization and QC remain separate.

Historical copy JSON stays evidence. `historical_receipts.reconcile(records,
observed_sizes)` reports possible size matches without claiming equivalence.
Its normalized input path/size fields require a future format-specific adapter;
raw records remain in evidence. Neither SNAP nor camera identity sets a game/role.

## Future FURG integration and remaining decisions

1. The existing copy tool must expose the exact selected local tree **after** final
   naming and all handles/writers have closed. Freeze it during hashing/save.
2. Obtain and persist the independent session UUID, participant and closure time;
   supply explicit rename provenance/exclusion reasons, never guessed mappings.
3. Call generate/save; transfer the exact tree and external sidecar. A failed or
   interrupted save requires inspection or a new destination, never overwrite.
4. The receiver independently associates UUID with a reviewed session root and
   calls verify after each arrival/retry. Only exact reception can advance to
   scientific review. No polling, server task or FURG software is installed here.

Pending human decisions: ownership of session UUID assignment/review, permitted
exclusion reasons and selection boundary, sender authentication/provenance policy,
and processing/QC authorization criteria. A unique unnumbered pair in a reviewed
session is now authorized as an inferred game classification, not as processing.
Actual FURG adapter wiring awaits its code. Real execution remains blocked.

Run `python -m pytest -ra` for all suites, and the three `test_*v2.py` /
`test_historical_receipts.py` files for new contract tests. Windows long-path
behavior follows the existing platform budget tests; no registry or privileges
are changed. CI uses Python 3.12 on Windows Server 2022 and Ubuntu, generated data
only. Hosted CI does not assert live FURG/Dell/NAS validation.
