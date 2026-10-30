# Proposed minimum operations — no DSM changes applied

This is a review matrix, not an ACL script or a grant. Windows execution identity
and SMB identity are distinct and must be validated by the administrator without
embedding credentials in source/config/logs. Ordinary UNC paths require no mapped
drive. No production credential or live server address is present in examples.

| Location | Future required operations | Forbidden / current gate |
|---|---|---|
| INBOX approved participant/session | list, read attributes, open/read bytes, hash | create/write/rename/delete forbidden; real access not exercised |
| RAW / historical originals | read only if independently authorized | all ingest/create/modify/delete blocked; immutable-originals mechanism unresolved |
| Local dedicated scratch | create/read/write temporary copies and outputs, local OS lock | must not overlap scientific roots; bounded pair, space check, manual retention |
| Local execution state | create/read, atomic local replacement, OS locking | never interpreted as scientific QC approval; no NAS lock equivalence assumed |
| SYNCED future publication namespace | list/read/verify; create directories; exclusive creation/write of NEW attempt files and completion record | no overwrite/delete/rename of existing results; currently no grant and integrated live publication blocked |
| LOGS_QC future namespace | read approved evidence; create immutable NEW provenance/journal exports after separate authorization | current implementation keeps journal local and manifest with synthetic result; automatic remote state/QC updates not enabled |
| CAMERA360, FaceReader, analytic data | none for synchronization | no ingestion or processing |

DSM inherited ACLs that permit modifying previously created files do not alone
enforce scientific immutability. The administrator must approve a mechanism that
allows new outputs/originals while protecting consolidated data, and verify its
interaction with ownership/inheritance. Application exclusive-create checks are
not a substitute for that decision. No broad Full Control permission is requested.
No raw ingestion, deletion or ACL/ownership escalation API is provided.

SMB protocol validation must establish exclusive create (`CREATE_NEW`/`O_EXCL`),
readback consistency and post-disconnect behavior. `fsync` on a client is not proof
of NAS durable storage after power loss. OS locks are only used on local state;
remote completion is validated by manifest/file hashes. A valid commit is required
for consumers, including a future monitor, to accept any output.
