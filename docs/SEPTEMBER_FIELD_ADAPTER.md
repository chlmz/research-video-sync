# September audio FFT — adapter for nested cohort field folders

> **Draft, locally tested on generated media; not a scientific QC approval or NAS production job.** This tool intentionally restores the **September 2026 batch script's** working approach, rather than forcing the later global Pearson-NCC and three-window consensus gate. It does **not** require claps, manual acoustic anchors or lowering NCC thresholds.
>
> The original source is [`sync_research_project.sh` at commit `0d3eedf`](https://github.com/chlmz/research-video-sync/blob/0d3eedf23f1b8c2b9314e475dbf5eca89787c06c/sync_research_project.sh). Use the **NumPy FFT route**, not the broken pure-Python fallback or `sync_videos.sh`.

## Exactly what we reused

- Read the whole audio track using FFmpeg, PCM mono **16 kHz** (the September default).
- RMS normalize mother and child signals; perform whole-recording FFT cross-correlation:

  ```python
  n = len(mom) + len(child) - 1
  corr = np.fft.irfft(np.fft.rfft(mom, n=n) * np.conj(np.fft.rfft(child, n=n)), n=n)
  k = int(np.argmax(corr))
  lag = k if k < len(mom) else k - n
  offset_seconds = lag / sample_rate
  ```

  The only mathematical correction to the legacy code is mapping FFT indices to the **true linear-lag support** when recordings are very unequal. The old half-array test could reverse the sign in that case.
- If `offset > 0`, trim the beginning of **mother**. If `offset < 0`, trim **child**. Keep the `-ss` trim *after* input before H.264/AAC re-encoding (`libx264`, `preset=fast`, `crf=22`, AAC `192k`).
- Generate **mother MP4, child MP4 and side-by-side MP4**, plus a local CSV/JSON report.

**This is the historical unqualified maximum**: it can return a false offset when audios differ or overlap poorly. The script does not claim scientific acceptance; each result is explicitly `CANDIDATE_FOR_MANUAL_QC`, `qc_status=NotApproved`. It does **not** silently promote a candidate as an approved alignment or publish to a scientific share.

## What was adapted for the field hierarchy

- Works with participant → **reviewed session root** → camera/date/DCIM/nested folders → role-numbered videos.
- Recursively finds `mother1.avi` and `children1.avi`, then `mother2.avi` and `children2.avi`, etc. Supported case-insensitive extensions: AVI, MP4, MOV, MKV. INSV/LRV, JSON and unrelated artifacts are not used as synchronization inputs.
- A session with one unique *unnumbered* `mother.avi`/`children.avi` pair is treated as game 1 **only because that whole session was explicitly selected**. Unnumbered files mixed with numbered games are not guessed. Duplicate role candidates are skipped with an issue.
- Does not infer sessions from camera A/B, SNAP numbers or dates. The local `field_sessions` configuration or `--session-root` explicitly defines which tree belongs to a session; this is necessary to prevent crossing games or visits.
- Output path is keyed by **participant / hashed session root / game**, avoiding repeated-output naming collisions. It is always on a local path **outside 00_INBOX, 01_RAW and other scientific source trees**.
- Reads source files, stages a verified local copy (SHA-256 comparison), extracts audio, creates MP4s and writes only to a new local diagnostic folder. Existing results never get overwritten; interrupted attempts remain available for inspection. **No source file is renamed, moved or deleted**.
- Does not change delivery.v2, the existing syncest, production tasks, NAS ACLs or automatic publication.

## Usage — dry-run, then local diagnostic export

Prerequisites: Python 3.12, NumPy and FFmpeg/FFprobe with `libx264` and AAC support. The repo's `requirements.txt` already contains NumPy. Commands below use **invented** IDs and paths; all actual configuration and logs stay private.

### Option A: nested layout through existing local `config.json`

`config.json` (never commit it) uses `followup_root`, `inbox` and `field_sessions` as already supported by the project. For example:

```json
{
  "followup_root": "D:\\SYNTHETIC_RESEARCH_FOLLOWUP",
  "inbox": "00_INBOX",
  "field_sessions": {
    "000003": ["delivery_A/session_1", "delivery_A/session_2"]
  }
}
```

The example above illustrates the fields of a **local config**, not a complete replacement for the application's regular `config.json`.

```powershell
# Review candidates without encoding or writing anything:
py -3.12 sync_september_field.py --config config.json --participant 000003 --output-root C:\ResearchScratch\september-qc

# Export all unambiguous games in reviewed sessions to a local QC directory:
py -3.12 sync_september_field.py --config config.json --participant 000003 --output-root C:\ResearchScratch\september-qc --execute

# Only game 1 if desired:
py -3.12 sync_september_field.py --config config.json --participant 000003 --game 1 --output-root C:\ResearchScratch\september-qc --execute
```

### Option B: a reviewed session without editing `config.json`

```powershell
py -3.12 sync_september_field.py --source-root C:\SyntheticFollowup\00_INBOX --participant 000003 --session-root delivery_A/session_1 --output-root C:\ResearchScratch\september-qc
py -3.12 sync_september_field.py --source-root C:\SyntheticFollowup\00_INBOX --participant 000003 --session-root delivery_A/session_1 --output-root C:\ResearchScratch\september-qc --execute
```

### Option C: two already identified local AVI copies

Use this for a single, previously selected pair when camera folders are not available locally. Role pairing is supplied explicitly, and the process does not touch the originals.

```powershell
py -3.12 sync_september_field.py --mom C:\SyntheticInputs\mom.avi --child C:\SyntheticInputs\child.avi --participant 000003 --session-root local_review --game 1 --output-root C:\ResearchScratch\september-qc
py -3.12 sync_september_field.py --mom C:\SyntheticInputs\mom.avi --child C:\SyntheticInputs\child.avi --participant 000003 --session-root local_review --game 1 --output-root C:\ResearchScratch\september-qc --execute
```

This is the most direct way to run a controlled *September-method* diagnostic on already verified local copies. **No manual clapping or event labeling is required.**

## Expected local results

```text
LOCAL_OUTPUT_ROOT/
  000003/
    session-<digest-of-reviewed-root>/
      game-01/
        000003_g01_mom_synced.mp4
        000003_g01_child_synced.mp4
        000003_g01_side_by_side.mp4
        sync_report.json
  sync_report_YYYYMMDDTHHMMSSZ_<suffix>.csv
```

`sync_report.json` records the original local paths, source hashes, FFT peak and lag, overlap, trims, output hashes/codecs/durations, and `qc_status=NotApproved`. **This report contains private metadata; do not upload it to GitHub or a public issue.**

## Local synthetic test evidence

The standalone implementation was checked with **11 targeted pytest cases**, including positive, negative, asymmetric and zero offsets; nested/multiple-game discovery; unique unnumbered session; duplicate and transfer blocking; original preservation, non-overwrite, and an end-to-end **three-MP4** FFmpeg run. All 11 passed in the initial local test environment. This is not a Dell/Windows/SMB or real scientific validation.

```powershell
py -3.12 -m pytest -q tests/test_september_field_adapter.py
```

## What this implementation intentionally does not do

It is not a replacement for the receipt protocol or automatic production scheduler. It does not claim `QCApproved`, convert arbitrary unnumbered sets into pairs, write to NAS `02_SYNCED`, or bypass the protected synthetic-only worker to achieve a live processing flag. The user-approved objective is to **recover the proven September workflow with a correct nested-folder adapter**, then inspect the local output before selecting a production publication policy.
