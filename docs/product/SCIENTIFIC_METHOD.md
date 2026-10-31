# Scientific synchronization method and QC — living specification

> **Status:** engineering specification grounded in code as of `a21279d6c7313d65eb1239e70f1bae3ae62b1420`. Only synthetic behavior has passed automated CI. The proposed wider-range FFT candidate stage is **not yet implemented at this reference SHA**. Scientific QC for actual recordings has not been approved.

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

The difference between recording durations is **not** the start-time offset. For example, durations 378.867 s and 220.800 s differ by 158.067 s, but could reflect unequal start **and/or end** times, incorrect container timestamps, or a different scientific episode.

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

## 5. Proposed wide-range candidate stage (not yet implemented at reference SHA)

The September whole-signal FFT search motivates an enhancement: propose offset candidates across a wider lag range, using memory-conscious techniques, and confirm each candidate with independent local windows plus the existing consensus/confidence criteria. Do not substitute an unnormalized global maximum for QC, and do not blindly raise `max_lag_seconds` just because the *durations differ*.

Acceptance tests must include at minimum:
- Known positive, negative and zero offsets.
- Realistic offsets greater than 120 seconds.
- Different recording durations and different start **and end** points.
- Different audio amplitudes, background noise, missing/shared audio and unrelated recordings.
- Repetitive acoustic patterns, silent intervals and coincident false peaks.
- Clock drift and interrupted streams (flag appropriately; do not claim fixed-offset correction).
- Controlled comparison to September's verified sign convention.
- Memory/time bounded behavior on long synthetic recordings.

When and only when the implementation is merged/released, replace this section with the actual algorithm, exact parameters, limits, SHA and evidence.

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

The responsible operator reported that a pair from a numbered game was copied to scratch with unchanged SHA-256 and timestamps, with mother/child container durations 378.867/220.800 s. Audio extraction passed, but **0/7 coarse windows** passed, median NCC **0.0207**, confidence **0**, and no offset was accepted. No synchronized MP4 were produced. The responsible researcher subsequently reported that the AVI play normally.

**Interpretation:** the pair is **not yet scientifically synchronized**. Plausible explanations include a lag outside ±120 seconds, insufficient shared acoustics, incorrect pair/session, or timestamp effects; none has been established. Do not present this as a failure of the cohort or as proof of video corruption.

## 9. Evidence and code references

- `rg2019/syncest.py` — algorithm, confidence and sign convention.
- `rg2019/media.py` — FFmpeg/FFprobe and encoding.
- `rg2019/synthetic_worker.py` — bounded synthetic worker with two MP4 outputs.
- `rg2019/delivery_v2.py` — independent receipt/manifest contract.
- `tests/test_syncest.py`, `tests/test_legacy_audit.py` — mathematical regression.
- `docs/VIDEO_SYNC_ENGINEERING_JOURNAL_WIP.md` — chronological evidence, errors and decisions.
- `docs/DELIVERY_V2.md` — acceptance of received files, **not** QC certification.
