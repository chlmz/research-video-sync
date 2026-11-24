# September full-audio FFT adapter

The adapter takes a reviewed mother–child pair and returns a local technical candidate for human QC. Supply the two prepared MP4s explicitly when an integration has already verified the session, game and take. Use a stable session key that includes the take, or a separate output root for each take.

```powershell
py -3.12 sync_september_field.py --mom C:\Synthetic\inputs\mom_source.mp4 --child C:\Synthetic\inputs\child_source.mp4 --participant 999999 --session-root synthetic-session/take-01 --game 2 --output-prefix ID999999_V01_G02_T01 --output-root C:\Synthetic\candidate --execute
```

Without `--execute`, the CLI prints the plan. The Python entry point is `execute_job(job, output_root, ffmpeg=..., ffprobe=..., output_prefix=..., max_offset_seconds=30.0, review_policy=ReviewPolicy())`. It returns the result directory and a report. A caller can pin the script by Git commit and SHA-256. NumPy, FFmpeg with libx264 and AAC, and FFprobe are required.

## Offset and review

FFmpeg extracts the full audio into mono, 16 kHz, signed 16-bit PCM. The estimator RMS-normalizes each recording, computes NumPy’s full linear FFT correlation, and selects its global maximum. If `k < len(mom)`, the lag is `k`. Otherwise it is `k - (len(mom) + len(child) - 1)`. This preserves the reference implementation for unequal recordings. A positive offset trims mother. A negative offset trims child. [September reference](https://github.com/chlmz/research-video-sync/blob/0a143d33862a274e3e9c8ed25495121218a9acac/sync_september_field.py)

The report records the peak and offset before testing the provisional 30-second limit. Reviewers can supply `--max-offset-seconds` and a JSON object via `--review-policy`. The following provisional defaults affect only the decision to withhold a trim.

| Setting | Default | Evidence assessed |
| --- | ---: | --- |
| min_overlap_seconds | 1 | Minimum usable audio and common audiovisual duration |
| distinct_lag_seconds | 0.05 | Minimum separation from the winning lag when checking for another plausible alignment |
| competing_peak_fraction | 0.80 | A distant value of the same raw FFT correlation reaching this fraction of the winning peak triggers review |
| quiet_pcm_level | 32 | Absolute sample level considered quiet in signed 16-bit PCM |
| min_active_fraction | 0.01 | Fraction of overlapping samples that must exceed the quiet level on each track |

Identical input bytes and audiovisual stream origins that differ beyond frame or AAC packet precision also trigger review. Record the effective settings alongside the report. The defaults support synthetic qualification. Scientific calibration and a disposition for each real candidate belong to the study’s review process. Two unrelated recordings can still yield an apparently isolated peak.

## Outputs and return codes

The results array printed by the CLI provides `output_folder`. Open `sync_report.json` there. It includes the selected lag, competing lag, overlap, effective review policy, source hashes, applied trims, output metadata and SHA-256 hashes. Reports for real inputs contain private metadata.

* `CANDIDATE_FOR_MANUAL_QC` returns 0 when every requested job succeeds. The three files use the supplied prefix plus `_mom_synced.mp4`, `_child_synced.mp4`, and `_side_by_side.mp4`. Mother is on the left. The three outputs cover their common audiovisual interval. Each passes an H.264/AAC stream, timing and full decode check.
* `NEEDS_REVIEW` returns 2 and writes the offset and review reasons. The report has empty `trims` and `outputs`.
* `FAILED` returns 2 and supplies the diagnostic in the results array. An interrupted working directory carries no candidate status.

Every technical result has `qc_status=NotApproved`. A completed result directory is immutable on rerun. The adapter stages input copies before processing and checks their SHA-256 against both sources.

## Standalone discovery

The older `--source-root`, `--participant` and `--session-root` options operate inside a deliberately selected session for standalone diagnostics. Files with explicit mother/child and game labels can form pairs. In this mode only, a single unnumbered pair inside an explicitly reviewed session can be treated as game one. A system with reviewed participant/session/game/take identities should use `--mom` and `--child` with the supplied game. SNAP numbers and A/B labels cannot establish a role or game.

## Reproduction

Run the synthetic tests with FFmpeg and FFprobe on PATH.

```powershell
py -3.12 -m pytest -q tests/test_september_field_adapter.py
```

The suite exercises asymmetric and signed lags, independent takes, ambiguous discovery, source preservation, repeated or silent audio, configurable review limits and output readback. Its explicit MP4 tests check both trim signs, panel order and a known 31.25-second offset that must be reported before any cut.
