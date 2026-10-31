# RG2019 Research Video Synchronization — Final Algorithm README

**Scientific product:** full-audio FFT synchronization of dual-camera mother–child interaction recordings, adapted to participant/session/game folders for the Coorte de Nascimentos de Rio Grande 2019 (RG2019).

> **FINAL SCOPE: the scientific synchronization logic, not the NAS pipeline.** The September 2026 full-audio NumPy FFT method has been adapted, generated three real pilot videos, and the investigator explicitly confirmed **perfect visual synchronization** of that pilot. This is a real, investigator-reviewed example, **not** a quantified error distribution, a multi-case validation or proof of unattended production readiness.
>
> **Reference code:** `sync_september_field.py`, exact tested implementation SHA [`0a143d33862a274e3e9c8ed25495121218a9acac`](https://github.com/chlmz/research-video-sync/commit/0a143d33862a274e3e9c8ed25495121218a9acac), branch `codex/gpis-september-field-adapter`, [draft PR #10](https://github.com/chlmz/research-video-sync/pull/10). This README was written **after** that code commit. It does not silently change the implementation or imply that the draft has been merged to `main`.
>
> **Public/private boundary:** algorithm, synthetic tests, formulas and generic folder structure are public. Participant media, real IDs, individual offsets, source hashes, machine names, share addresses, ACLs, credentials and operational logs are private and must never be committed to this repository.

## 1. Research problem and outputs

For two recordings of the **same** interaction that were started at different times:

1. Identify an unambiguous **mother + child** pair within a reviewed participant, session and game.
2. Read verified **copies** of the original videos; do not alter research sources.
3. Extract the complete audio stream from each camera, mono, 16 kHz, signed 16-bit PCM.
4. Compute the global audio delay with the **September NumPy FFT correlation** — no ±120 s search limit, no Pearson/NCC threshold, no mandatory clap or manual event labeling.
5. Remove the **leading** segment only from the camera that began earlier, based on the mathematically verified sign convention.
6. Encode two H.264/AAC MP4s and one **mother-left / child-right** side-by-side MP4.
7. Record provenance, source/output SHA-256, offset and media properties in private local JSON/CSV reports. The generated files are review candidates until the study's QC process records their disposition.

The **unit of processing** is `participant × independently reviewed session × game`. Never mix games or visits based on sorted filenames, timestamps, camera A/B or SNAP numbers.

## 2. Provenance: exactly what was reused

| Component | Source or evidence | Interpretation |
| --- | --- | --- |
| Original implementation | [`sync_research_project.sh`, initial September 2026 commit](https://github.com/chlmz/research-video-sync/blob/0d3eedf23f1b8c2b9314e475dbf5eca89787c06c/sync_research_project.sh) | Historical, working **NumPy** full-audio FFT, trim and three-video export; reported useful in earlier pilots |
| Historical errors | [`docs/LEGACY_AUDIT.md`](docs/LEGACY_AUDIT.md) and `tests/test_legacy_audit.py` | A **different** script (`sync_videos.sh`) trimmed the wrong camera; old Bash batch/fallback/overwrite behavior was unsafe |
| Adaptation | [`sync_september_field.py`](sync_september_field.py), code SHA above | The same NumPy FFT approach with corrected lag index for unequal durations, nested sessions/games and safe local outputs |
| Synthetic tests | [`tests/test_september_field_adapter.py`](tests/test_september_field_adapter.py) | **12 focused local tests** reported passing, including actual FFmpeg generation of three synthetic MP4s |
| Real pilot | Authorized Work execution and investigator review, held **privately** | All three MP4 exported; operator reported no FFmpeg failure and unchanged source-copy hashes; investigator subsequently confirmed perfect visual alignment |

The later guarded Pearson/NCC estimators have different rejection logic and were not substituted into the final September-style adapter. Their unsuccessful private attempts remain in the [sanitized engineering history](https://github.com/chlmz/research-video-sync/blob/docs/video-sync-technical-journal/docs/VIDEO_SYNC_ENGINEERING_JOURNAL_WIP.md), not in this algorithm's execution path.

## 3. Exact mathematical method

### 3.1 Extract **all** audio at 16 kHz

FFmpeg extracts the **first** audio stream from each source, mixing to mono and resampling to little-endian signed PCM 16-bit WAV at **16,000 samples/s**, the September default:

```text
ffmpeg -nostdin -hide_banner -loglevel error -n -i INPUT_VIDEO \
  -map 0:a:0 -vn -ac 1 -ar 16000 -c:a pcm_s16le -f wav OUTPUT.wav
```

The Python implementation executes FFmpeg with argument arrays, not by interpolating file names into a shell command. The adapter offers `--sample-rate 8000` as an alternative, but **16 kHz is the reference method used for the successful real pilot**.

### 3.2 RMS-normalize both full-length signals

Read the PCM samples into NumPy arrays. For a signal $x$ with $L$ samples:

\[
\mathrm{RMS}(x)=\sqrt{\frac{1}{L}\sum_{i=0}^{L-1}x_i^2},\qquad
\tilde x_i=\frac{x_i}{\mathrm{RMS}(x)}.
\]

Do this separately for mother and child, using the **entire audio track**. The code uses a denominator of 1 if the RMS is zero to avoid division by zero; this **does not establish that silent audio is synchronizable**. RMS scaling is not overlap-specific normalized cross-correlation (NCC), a noise-removal procedure or a calibrated confidence score.

### 3.3 Global FFT cross-correlation — no window restriction

If the full normalized mother array is $a$ of length $M$ and the child array is $b$ of length $N$, the desired linear cross-correlation is:

\[
C(k)=\sum_{j\text{ in overlap}}a_{j+k}\,b_j.
\]

The **executed** NumPy strategy is:

```python
n = len(mom) + len(child) - 1
FA = np.fft.rfft(mom, n=n)
FB = np.fft.rfft(child, n=n)
corr = np.fft.irfft(FA * np.conj(FB), n=n)
k = int(np.argmax(corr))
lag = k if k < len(mom) else k - n
offset_seconds = lag / sample_rate
```

Here `mom` and `child` mean the **RMS-normalized, full-length** sampled audio. The lag search spans the entire valid linear-correlation support, **not** the ±120-second range of the older pure-Python fallback or the later windowed estimator.

**Single mathematical correction from September:** the historical NumPy snippet converted an FFT index to negative lag with `if k > n//2: k -= n`. That half-array heuristic can produce the wrong sign for **strongly unequal recording durations**. The actual support is `-(N-1) … (M-1)`. Thus the reviewed adapter instead uses `lag = k if k < M else k - n`; its focused tests check the sign for asymmetric inputs.

The algorithm selects the **unqualified raw-correlation maximum**. This is intentionally faithful to September's functioning NumPy route. It can return a numerically well-defined but **incorrect** offset for unrelated or weakly shared audio. Do not equate a global maximum with scientific certainty or reintroduce the stricter NCC gate as if it were already part of this version.

### 3.4 Sign of the offset: critical invariant

For a common sound at time $t_{\mathrm{mom}}$ in mother and $t_{\mathrm{child}}$ in child:

\[
\Delta=t_{\mathrm{mom}}-t_{\mathrm{child}}.
\]

| Offset | Which camera started first? | Action |
| --- | --- | --- |
| `Δ > 0` | **Mother** started earlier | **Trim Δ seconds from the start of MOTHER** |
| `Δ < 0` | **Child** started earlier | **Trim abs(Δ) seconds from the start of CHILD** |
| `Δ = 0` | Same start | No leading trim |

**Invented example:** an acoustic event appears at 17 s in mother and 2 s in child: `Δ = +15 s`, so mother is trimmed by 15 s and child is not trimmed. The difference between the *durations* of two recordings **is not** their start-time offset. Do not reuse `sync_videos.sh` or invert this sign.

### 3.5 Re-encode both individual views

The current adapter always **re-encodes both** mother and child MP4s, even the untrimmed view. Its FFmpeg encoding settings are:

```text
ffmpeg -nostdin -hide_banner -loglevel error -n -i INPUT_VIDEO \
  [-ss LEADING_TRIM_SECONDS] \
  -map 0:v:0 -map 0:a:0 \
  -c:v libx264 -preset fast -crf 22 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart \
  -f mp4 OUTPUT.mp4
```

`-ss` is added **after** `-i` only when the leading trim is positive (frame-accurate decode/re-encode behavior). Existing outputs are not overwritten (`-n`). The two MP4s are not additionally cropped to an equal endpoint and may have different durations.

### 3.6 Create mother-left / child-right composition

The side-by-side output uses these equivalent FFmpeg filter stages:

```text
[0:v]scale=-2:720,setpts=PTS-STARTPTS[left];
[1:v]scale=-2:720,setpts=PTS-STARTPTS[right];
[left][right]hstack=inputs=2:shortest=1[v];
[0:a][1:a]amix=inputs=2:duration=shortest[a]
```

The composition is then encoded in H.264 (`libx264`, `fast`, CRF 22, `yuv420p`) and AAC 192k. The side-by-side ends at the shorter view; mother is **left**, child **right**. This is the visual QC artifact that the investigator inspected in the successful pilot.

## 4. Field folder adaptation — what is and is not inferred

The scientific method does not depend on one flat folder. A **reviewed session** can have many camera/DCIM subfolders and several numbered games, e.g. this **invented** tree:

```text
SOURCE_ROOT/
  000003/
    visit_A/
      CAM_A/DCIM/mother1.avi
      CAM_B/DCIM/children1.avi
      CAM_A/DCIM/mother2.avi
      CAM_B/DCIM/children2.avi
      camera_360/auxiliary.insv
      transfer-log.json
    visit_B/
      CAM_A/mother1.avi
      CAM_B/children1.avi
```

- A reviewed `field_sessions` mapping or `--session-root` defines the **session boundary**. The adapter does not infer sessions from dates, the camera identifier or SNAP sequence.
- The role parser recognizes `mother/mom` and `children/child` (case-insensitive) and an **attached** game number 1–99 in the filename or subordinate path component.
- Exactly **one** mother and **one** child candidate per game are needed; duplicate/missing/contradictory role cases are reported for review instead of taking the first file.
- One unique **unnumbered** mother/child pair can become game 1 only inside an explicitly reviewed single-pair session. Mixed numbered and unnumbered candidates remain ambiguous.
- AVI, MP4, MOV, MKV are candidate video containers; INSV/LRV and historical JSON are auxiliaries, **not** a replacement for reviewed pair identity.
- Transfer-in-progress files and symbolic links/junctions trigger conservative warnings or blocking. This recognition **does not guarantee completeness of the field delivery**; receiving and RAW admission are distinct future integration steps.

## 5. Code, inputs, outputs and reproducibility

**Public source file:** [`sync_september_field.py`](sync_september_field.py) at the pinned tested SHA. **Tests:** [`tests/test_september_field_adapter.py`](tests/test_september_field_adapter.py). **Earlier practical guide:** [`docs/SEPTEMBER_FIELD_ADAPTER.md`](docs/SEPTEMBER_FIELD_ADAPTER.md).

**Requirements:** Python 3.12, NumPy (`requirements.txt`), FFmpeg and FFprobe with `libx264` and AAC support; enough **local** RAM and scratch space. The full-audio FFT uses memory proportional to recording length and has **no enforced RSS cap**.

On Windows PowerShell, from a development checkout:

```powershell
git clone https://github.com/chlmz/research-video-sync.git
cd research-video-sync
git fetch origin codex/gpis-september-field-adapter
git checkout --detach 0a143d33862a274e3e9c8ed25495121218a9acac
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q tests/test_september_field_adapter.py
```

**Planning mode by default:** with synthetic or authorized input, omit `--execute` to list selected jobs without encoding:

```powershell
.\.venv\Scripts\python.exe sync_september_field.py `
  --source-root "C:\SyntheticStudy\00_INBOX" `
  --participant 000003 --session-root "visit_A" `
  --output-root "C:\SyntheticScratch\video-qc"
```

**Local execution on synthetic files only** (use a **new, empty local** output root, never an existing research output directory):

```powershell
.\.venv\Scripts\python.exe sync_september_field.py `
  --source-root "C:\SyntheticStudy\00_INBOX" `
  --participant 000003 --session-root "visit_A" `
  --output-root "C:\SyntheticScratch\video-qc-new" --execute
```

If a pair has already been **explicitly reviewed and copied locally**, the adapter also accepts `--mom`, `--child`, one `--participant`, one `--session-root` and `--game` instead of walking folders. Do not point the script at a live, changing field delivery or an unauthorized NAS share; the full receiving process is not implemented here.

**Generic output layout:**

```text
LOCAL_QC_OUTPUT/
  000003/
    session-<12-char-hash-of-reviewed-session-root>/
      game-01/
        000003_g01_mom_synced.mp4
        000003_g01_child_synced.mp4
        000003_g01_side_by_side.mp4
        sync_report.json
  sync_report_<UTC-date>_<unique-suffix>.csv
```

**Source protection:** the adapter copies input files to a new scratch location, compares the source/copy SHA-256, encodes a new output attempt, probes audio/video presence and writes output hashes. It does **not** move source media, overwrite an existing destination or write to NAS. A completed local output directory is renamed from its temporary attempt directory. This source-level discipline does not imply that external NAS ACLs have been configured.

**Private metadata:** `sync_report.json` stores source paths, participant/session/game, input hashes, the FFT peak, computed offset and overlap, trims, output hashes and technical information. It carries `status=CANDIDATE_FOR_MANUAL_QC` and `qc_status=NotApproved`. On real subjects the report and the three MP4s must stay inside the authorized **private** research environment.

## 6. Validation and limitations — what is actually finished

**Completed for the reference method:**

- **[CODE]** September full-audio NumPy FFT, corrected linear lag for unequal recordings, positive-trim-mother rule, frame-accurate FFmpeg re-encoding of both views, and side-by-side composition.
- **[TEST]** 12 focused synthetic tests reported passing, including sign/lags, multiple games, ambiguity, source hashes, overwrite protection and actual three-MP4 output on generated media.
- **[FIELD REPORT]** Authorized Work execution reported completion of all three MP4s on one real pilot and preservation of original-copy hashes.
- **[MANUAL REPORT]** The responsible investigator expressly confirmed **perfect visual synchronization** of that pilot.

**Not demonstrated or not yet operational:** a calibrated millisecond error tolerance, drift correction, generalization to all participant pairs, false-positive rate on unrelated audio, remote NAS delivery monitoring, automatic RAW admission, automatic publication to SYNCED, full ACL enforcement or an unattended scheduler.

The September method's raw global maximum is intentionally *not a scientific confidence probability*. Silence, weakly related recordings, repetition and microphone differences can produce a misleading offset. Use the side-by-side for visual review; record formal approval according to a separate, approved study QC policy. The existing code still labels all derived files **`NotApproved`** automatically; the investigator's positive visual judgment has been recorded separately, not used to silently relabel machine reports.

The reference is **frozen by tested code SHA**; documentation fixes do not alter that code. Any proposed mathematical revision must be a new reviewed version with regression tests and explicit comparison to the functioning September-method pilot. Do **not** silently reintroduce the later normalized NCC/window gates as a prerequisite, require claps or infer session/game by date.

## 7. Independent AI reproduction guide

To adapt this product for another study, a human or AI must:

1. Read this document, the exact pinned `sync_september_field.py`, `tests/test_september_field_adapter.py` and `docs/LEGACY_AUDIT.md`. Do **not** use `sync_videos.sh` or the broken Python fallback in the old Bash script.
2. Preserve **16 kHz complete mono PCM → whole-signal RMS normalization → FFT linear correlation → corrected lag sign → trim earlier camera** unless proposing a scientifically different algorithm under a new version.
3. Preserve **mother/child output + side-by-side** and original-file integrity/provenance. Use only synthetic fixtures in public development environments.
4. Explicitly map the new study's participant/session/game hierarchy without silently guessing matching pairs.
5. Test positive/negative/zero, strongly unequal durations, duplicate/missing pairs and three-output FFmpeg encoding; measure memory for long synthetic media.
6. Keep **technical export success, a human visual report and formal QC approval** distinct. Do not invent accuracy statistics or claim clinical/automatic validation from one visually successful pilot.
7. Keep server, NAS, accounts, backup, ACLs, secrets reference and publishing state machines in an **access-controlled operational runbook**, never in the public algorithm's README or GitHub issues.

**Self-contained AI handoff:** “Reproduce the September NumPy full-audio FFT synchronizer at code SHA `0a143d33862a274e3e9c8ed25495121218a9acac`: extract 16-kHz mono WAV from each source, RMS normalize each whole signal, calculate `irfft(rfft(mom)*conj(rfft(child)))` with full linear length, correct index mapping for unequal durations, positive offset trims mother, negative trims child. Re-encode mother, child, side-by-side H.264/AAC videos. Discover explicit participant/session/game pairs in nested folders; do not overwrite or change originals. Protect real data and keep NAS transport and publishing separate.”

## 8. Public algorithm versus private NAS processing

This public README documents **how to synchronize**, not how the GPIS network is configured. The planned private operational flow is:

```text
00_INBOX  -- verified complete delivery / hashes --> 01_RAW (protected originals)
                                                    |
                                  read-only source + local scratch copy
                                                    |
                                         SEPTEMBER FFT SYNCHRONIZER
                                                    |
                                           three derivative MP4s
                                                    |
                        technical/scientific review + publication authorization
                                                    v
                                               02_SYNCED
```

The current adapter **does not implement these transitions**: it can calculate offsets and create the three MP4s on local copies, but does not admit arrivals into `01_RAW` or publish outputs into `02_SYNCED`. The historical `pipeline_rg2019.py` that **moved** flat participant folders from INBOX to RAW is **not** an approved substitute for the present nested session/game structure. Do not deploy the old move behavior against current research directories.

Actual NAS identities, hostnames, addresses, ACLs, permissions, copy-vs-move mechanics, immutable source handling, staging, atomic publication, backups, retry and recovery must remain documented separately in a **private GPIS runbook**. An external researcher can reproduce this algorithm without knowing any of that private infrastructure.

## 9. Publication and versioning status

This is the **final specification of the tested synchronization algorithm**, not an assertion that a fully deployable research-software release exists. As checked for the referenced branches, there is no confirmed approved `LICENSE`, `CITATION.cff`, tagged software release or DOI; public visibility alone does **not** define permission to reuse under an open-source license. Credits, funding, release identity and a permanent citation must be approved before official dissemination as a software release.

Keep the long-form [sanitized engineering history](https://github.com/chlmz/research-video-sync/blob/docs/video-sync-technical-journal/docs/VIDEO_SYNC_ENGINEERING_JOURNAL_WIP.md) for development mistakes and rationale, and the [public/private policy](https://github.com/chlmz/research-video-sync/blob/docs/video-sync-technical-journal/docs/product/PUBLIC_PRIVATE_POLICY.md) for disclosure controls.