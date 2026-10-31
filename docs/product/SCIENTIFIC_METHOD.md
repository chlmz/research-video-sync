# Scientific synchronization method and QC — living specification

> **Status:** engineering specification. The underlying documented contract v2 is `a21279d6c7313d65eb1239e70f1bae3ae62b1420`; the new FFT option is implemented **only in separate unmerged [draft PR #9](https://github.com/chlmz/research-video-sync/pull/9)** at `5cbd7ddad928d36b774476f0a34e28317fff5bc4`. Only synthetic behavior has passed CI; real scientific synchronization has not been approved.

## 1. Scientific problem and unit of analysis

Two cameras observe the same mother/child interaction, potentially starting at different absolute times and ending at different times. The scientific observation is **participant + independently identified session + game**; a six-digit participant ID is not a session ID. A single participant can have multiple games, and game numbers can recur across sessions.

A paired candidate is not automatically a complete delivery. A complete delivery is not necessarily a valid scientific pair. A technically encoded video is not automatically synchronized to scientific standards.

The principal expected derived videos, once authorized, are a synchronized mother view and a synchronized child view, plus an optional or required QC-oriented side-by-side. The safe synthetic preproduction demo currently produces only two individual MP4s and `sync.json`; **the side-by-side is not fully integrated into that safe executor**.

## 2. Ground-truth time and the sign convention

Let one acoustic event be observed at `t_mom(e)` seconds in the mother's media timeline and at `t_child(e)` seconds in the child's.

```text
offset_seconds = t_mom(e) - t_child(e)

offset > 0 → mother recording started earlier → trim offset from mother start
offset < 0 → child recording started earlier  → trim abs(offset) from child start
offset = 0 → no leading trim
```

This is fixed in `rg2019/syncest.py` and verified by `tests/test_syncest.py` and `tests/test_legacy_audit.py`. **Do not reverse the sign**. A September two-file shell utility mistakenly trimmed the *other* camera; do not reuse it.

The difference between recording durations is **not** the start-time offset. In an **invented example** with 400 s and 220 s of recordings, the 180 s duration difference could reflect unequal start **and/or end** times, incorrect container timestamps or a different scientific episode; it does not prove the lag.

The present method estimates a **constant offset**. Disagreement between windows can indicate noise, mispairing or clock drift; it does not correct drift.

## 3. Historical September method

The original cohort batch script `sync_research_project.sh` (initial commit `0d3eedf23f1b8c2b9314e475dbf5eca89787c06c`) extracted WAV audio at **16 kHz** and used an FFT-based correlation over the **entire** audio streams with NumPy, without a fixed ±120-second search bound in that route:

```python
n = len(mom) + len(child) - 1
A = np.fft.rfft(mom, n=n)
B = np.fft.rfft(child, n=n)
correlation = np.fft.irfft(A * np.conj(B), n=n)
lag = int(np.argmax(correlation))
if lag > n // 2:
    lag -= n
offset_seconds = lag / sample_rate
```

This is conceptual historical code, **not a validated production estimator**. Tests established correct sign and trims for controlled synthetic ±5 s, ±20 s and 0 s cases in its NumPy path. It can search a wide interval but uses substantial memory for long signals and **always returns a maximum**, even with unrelated or weak audio. It lacks independent confidence criteria.

Its pure-Python fallback produced erroneous offsets in regression tests. The other old script (`sync_videos.sh`) trimmed the wrong video. Both also have unsafe file handling. See [legacy audit](../LEGACY_AUDIT.md).

## 4. Windowed estimator in the reviewed Python commit

Read the executable reference `rg2019/syncest.py` and dataclass defaults `rg2019/config.py` before changing any of these values.

1. FFmpeg extracts the **first audio stream** of each source as mono, signed 16-bit PCM at 8 kHz. It stores samples on disk and reads via a memory map to avoid holding entire recordings in RAM. Video decoding errors may be independent of successfully extracted PCM.
2. The signal preprocessing removes the DC component and applies first-order pre-emphasis, reducing common low-frequency rumble.
3. **Coarse stage:** distribute up to **7 distinct 60 s windows** over the possible overlap; search each within **±120 s**. Normalized cross-correlation (NCC) uses FFT convolution. A window needs **NCC ≥ 0.05** and a highest-to-competing-peak ratio **≥ 1.5**.
4. Infer a coarse offset only if at least **two** valid windows form an agreeing cluster within the coarse tolerance (default **0.5 s**).
5. **Fine stage:** search up to **5 distinct windows** across overlap within **±2 s** of the coarse candidate. Each must start far enough from the others (at least half a window apart); use peak interpolation.
6. Accept only if at least **3** fine windows agree within **0.25 s**, agreeing proportion **≥ 0.6**, and their median NCC reaches the configured minimum. The estimate also records offset spread, median peak ratio, per-window evidence and confidence.
7. If any gate fails, return **LOW_CONFIDENCE**; do not generate automatically accepted scientific outputs.

The default `min_ncc=0.05` and other thresholds are implementation values, **not yet externally calibrated scientific acceptance thresholds**. The pipeline must not silently adjust them to make a difficult pair pass.

## 5. Optional global FFT candidate search — unmerged draft PR #9

[Draft PR #9](https://github.com/chlmz/research-video-sync/pull/9) implements the optional global candidate search at commit `5cbd7ddad928d36b774476f0a34e28317fff5bc4`. The [mathematical reference](https://github.com/chlmz/research-video-sync/blob/5cbd7ddad928d36b774476f0a34e28317fff5bc4/docs/GLOBAL_FFT.md) is version-pinned. **The feature is not in the baseline #7 SHA, not merged/released and disabled by default. No field recording has passed it yet.**

The September unqualified whole-audio maximum and its circular half-length lag interpretation are **not** reused. The Python implementation uses FFT convolution with reversed child audio and valid linear lags `-(N-1)..(M-1)`. Its whole-overlap correlation is locally mean- and variance-normalized (Pearson NCC), using prefix sums:

```text
C(k) = Σ_j mom[j+k] * child[j]
NCC(k) = (C(k) - S_m*S_c/n) / sqrt((Q_m-S_m²/n)*(Q_c-S_c²/n))
```

Here `n` is the overlap length and `S_m`, `S_c`, `Q_m`, `Q_c` are sums and squared sums **within that overlap**. Minimal-overlap and effectively silent peaks are excluded. The largest distinct peaks merely **propose** candidate lags; they do not establish scientific synchronization.

Each proposal is independently validated with **disjoint windows**, local NCC/peak-ratio criteria, agreement tolerance and fraction, and at least **three** agreeing windows. Exactly **one** independently validated candidate must remain. Unknown/unrelated audio and plausible competing offsets remain blocked. The correct mother-positive sign convention and audio-stream timestamp adjustment are unchanged.

| Option at experimental SHA | Default | Notes |
|---|---:|---|
| `global_fft_enabled` | `false` | Explicit opt-in only |
| `global_fft_candidates` | 3 | Accepted range 2–8 |
| `global_fft_memory_mb` | 512 MiB | Accepted range 1–4096 MiB; estimate, **not** a hard RSS cap |
| `sample_rate` | 8 kHz | Audio analysis, full resolution |
| `window_seconds` | 60 s | Disjoint validation |
| `fine_search_seconds` | 2 s | Local confirmation |
| `min_agreeing_windows` | 3 | Required consensus |

The memory admission formula is `192*next_fast_len(M+N-1)+64*(M+N)` **bytes** plus separate validation-window checks; the formula omits caller-owned PCM and operating-system/library overhead. A **hypothetical** ~600 s combined recording at 8 kHz would need approximately **1,172 MiB estimated additional workspace**, so the default 512 MiB (and 1024 MiB) would block. Sample counts and free RAM must be checked locally before deliberately choosing any larger experimental budget. Do not use a large budget as a substitute for scientific validation.

**Synthetic CI verified at exactly this SHA:** [Actions run 41161224041](https://github.com/chlmz/research-video-sync/actions/runs/41161224041): Windows 309 passed; Ubuntu 308 passed and one Windows-specific junction test skipped; zero failures. The 13 new tests are **included** in the totals. They address ±180 s and ±350 s offsets, asymmetry, unrelated and repetitive sound, memory admission, timestamp adjustment and immutable inputs. This does **not** mean that a real participant has been synchronized.

**Next gate:** authorize one diagnostic estimator call on already-preserved local audio copies, verify sample rate, free RAM and actual sample counts, and record candidate/window evidence without editing sources or enabling the guarded real-media pipeline. The synthetic worker's **120 s input limit remains intact**. All scientific QC remains `NotApproved`.

## 6. AVI and codec handling

AVI, MP4, MOV and MKV are containers; H.264 is a video codec; PCM and AAC are audio codecs. In one controlled real pilot (reported 2026-10-30), the source files were AVI containing H.264 Main video and PCM mono 16-kHz audio. FFmpeg extracted audio, while some H.264 decoder warnings occurred; the researcher reported normal visual playback. These observations neither prove all frames decode correctly nor establish that the original was irrecoverably damaged.

Do not rename an AVI extension to MP4 to "repair" the video. If remux or transcode is required after diagnostic evidence, operate on verified local copies, preserve original bytes and hashes, document software/parameters and confirm A/V timestamps and decode results before accepting outputs.

The encoding API `rg2019/media.py` normally re-encodes a trimmed camera for frame-accurate start cuts (H.264/AAC MP4). An untrimmed source can be stream-copied only when both codecs are compatible with the target container; PCM audio in AVI does not meet the script's stream-copy compatibility gate. The old shell scripts are not approved as fallback exporters.

## 7. End-to-end scientific validation for real recordings

**This protocol is proposed for validation; completion has not yet been demonstrated.**

1. Confirm participant/session/game mappings through evidence independent of names and dates; ensure no additional viable pair conflicts.
2. Verify reception manifest plus SHA-256 for all declared files. Preserve originals as read-only evidence. Locate independent session UUID and delivery ID.
3. Characterize duration, actual audio/video streams, timestamps, FPS and any reproducible decoder corruption. Require an adequate overlap.
4. Compute an offset candidate from audio, preserve all window metrics and alternative peaks, and reject insufficient confidence without forcing acceptance.
5. Check recut sign convention, expected overlap, changed data, and no unexpected channel substitution.
6. Encode **on local scratch only** using immutable output attempts; validate MP4 decoding, audio/video durations, absence of new corruption and hashes.
7. Independently review the **start, middle and end** of the overlap. Inspect at least two identifiable shared events separated in time, if available, to estimate offset and possible clock drift. Seek manual review if the event is not recognizable.
8. Record a review decision and responsible reviewer; document scientific tolerance for residual offset and drift **before** claiming a pass. No arbitrary numeric acceptance threshold is established here.
9. Only after explicitly approved publication and ACL checks may derived videos be written to the research outputs. `TechnicalSuccess`, `Published` and `ReceptionVerified` are **not** scientific `QCApproved`.
10. Document failures and retain evidence, including cases that require different pairing or cannot be synchronized acoustically.

Suggested structured QC record (fields, not invented results): study/pipeline version, pseudonymous session identifier (private), source SHA (private), algo/parameters, audio estimate and confidence, independent event checks, start/middle/end observations, video decoder results, final disposition, reviewer, review date, immutable report pointer.

## 8. Actual evidence from first controlled real pilot (report only)

The responsible operator reported that a pair from a numbered game was copied to controlled local scratch with unchanged original/copy SHA-256. Audio extraction passed, but coarse-window consensus was insufficient; no offset was accepted and no synchronized MP4 were produced. The researcher reported that both AVI played normally. **Exact real-media durations and individual acoustic metrics are retained in private QC evidence, not this public document.**

**Interpretation:** the pair is **not yet scientifically synchronized**. Plausible explanations include a lag outside the earlier ±120-second search, insufficient shared acoustics, incorrect pairing or timestamp effects; none has been established. The optional global FFT has not yet been tested with these private recordings. Do not present this as a failure of the cohort or as proof of video corruption.

## 9. Evidence and code references

- `rg2019/syncest.py` — algorithm, confidence and sign convention.
- `rg2019/media.py` — FFmpeg/FFprobe and encoding.
- `rg2019/synthetic_worker.py` — bounded synthetic worker with two MP4 outputs.
- `rg2019/delivery_v2.py` — independent receipt/manifest contract.
- `tests/test_syncest.py`, `tests/test_legacy_audit.py` — mathematical regression.
- `docs/VIDEO_SYNC_ENGINEERING_JOURNAL_WIP.md` — chronological evidence, errors and decisions.
- `docs/DELIVERY_V2.md` — acceptance of received files, **not** QC certification.
