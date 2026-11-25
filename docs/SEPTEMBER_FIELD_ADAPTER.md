# September full-audio FFT adapter

The adapter takes a reviewed mother–child pair and returns a local technical candidate for human QC. Supply the two prepared MP4s explicitly when an integration has already verified the session, game and take. Use a stable session key that includes the take, or a separate output root for each take.

```powershell
py -3.12 sync_september_field.py --mom C:\Synthetic\inputs\mom_source.mp4 --child C:\Synthetic\inputs\child_source.mp4 --participant 999999 --session-root synthetic-session/take-01 --game 2 --output-prefix ID999999_V01_G02_T01 --output-root C:\Synthetic\candidate --execute
```

Without `--execute`, the CLI prints the plan. The Python entry point is `execute_job(job, output_root, ffmpeg=..., ffprobe=..., output_prefix=..., max_offset_seconds=30.0, review_policy=ReviewPolicy())`. It returns the result directory and a report. A caller can pin the script by Git commit and SHA-256. NumPy, FFmpeg with libx264 and AAC, and FFprobe are required.

## Offset and review

FFmpeg extracts the full audio into mono, 16 kHz, signed 16-bit PCM. The estimator RMS-normalizes each recording, computes NumPy’s full linear FFT correlation, and selects its global maximum. If `k < len(mom)`, the lag is `k`. Otherwise it is `k - (len(mom) + len(child) - 1)`. This preserves the reference implementation for unequal recordings. A positive offset trims mother. A negative offset trims child. [September reference](https://github.com/chlmz/research-video-sync/blob/0a143d33862a274e3e9c8ed25495121218a9acac/sync_september_field.py)

An absolute offset above 30 seconds adds `LARGE_OFFSET_REVIEW` to the report's `warnings` and requests visual review. The adapter produces all three MP4s when the technical checks pass. The equality boundary is inclusive of ordinary offsets. Set the warning threshold with `--max-offset-seconds`. The estimator always searches the full audio. A JSON object supplied through `--review-policy` configures the separate technical checks.

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

Each candidate carries `qc=PENDING`, the compatible `qc_status=NotApproved` field and a visual review request. Successful candidates have an empty `review_reasons` list. An independently failing technical check can coexist with a warning. A completed result directory is immutable on rerun. The adapter stages input copies before processing and checks their SHA-256 against both sources.

## AVI preparation

For AVI inputs the adapter counts timestamped decoded audio samples, checks continuity, and compares the result against the length of the PCM extracted for the FFT. The private report retains the container's declared audio duration alongside the measured duration.

An integrator that converts AVI to MP4 before calling the adapter can run its preparation command on a verified original. Supply a new file path under private local scratch.

```powershell
py -3.12 -I sync_september_field.py prepare-headcam C:\Synthetic\inputs\source.avi C:\Synthetic\scratch\retained.avi
```

Exit 0 prints a JSON receipt. Mode `original` means the entire input passed strict audiovisual decoding and the caller reads the original. Two modes supply a new scratch AVI for H.264 and 16-bit PCM.

- `pcm_header_normalized` handles a demux rejection of a PCM sample-size value of −1. The adapter checks the RIFF stream headers, channel count, sample width, block alignment and byte rate. It changes the single four-byte sample-size field on a verified copy, checks the timestamped sample clock, then repeats strict decoding.
- `terminal_zero_packet_removed` requires a declared, contiguous video packet inventory, the specific FFprobe missing-picture diagnostic, the matching terminal packet size and an entirely zero payload at the reported file position. Every retained packet must preserve its SHA-256, timestamp and duration. The check decodes every retained frame, compares the frame timeline, and verifies the full PCM digest and sample clock. The receipt records both file hashes, the excluded packet, the retained timeline digest, the exclusive end timestamp and the video time base. A combined correction also carries the `pcm_header` proof.

Exit 2 holds the input for review. Keep the resulting scratch file and receipt private. Direct AVI pair processing applies these checks internally.

## Standalone discovery

The older `--source-root`, `--participant` and `--session-root` options operate inside a deliberately selected session for standalone diagnostics. Historical role and number labels can form a pair. A single unnumbered pair in that session receives the legacy numeric slot 1. Each study visit has one activity and can have repeated recordings. The integrator supplies `--mom` and `--child` after reviewing the physical pair and the roles for that visit. A/B labels denote complementary devices. Headcam discovery excludes 360 folders, INSV and LRV.

## Reproduction

Run the synthetic tests with FFmpeg and FFprobe on PATH.

```powershell
py -3.12 -m pytest -q tests/test_september_field_adapter.py
```

The suite exercises asymmetric signed lags, ambiguous discovery, source preservation, repeated and silent audio, overlap holds and configurable offset warnings. Its MP4 tests verify both signs beyond 30 seconds, the boundary at 30 seconds, panel order, and full decoding. Its AVI tests synthesize an incorrect audio header and isolated, interior, nonzero, and multiple damaged packet cases. Run `python -m pytest -q` for the complete repository suite.
