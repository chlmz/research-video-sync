# Global FFT candidate search: mathematical design

Historical source: `sync_research_project.sh` at
`0d3eedf23f1b8c2b9314e475dbf5eca89787c06c`, NumPy path only. Current baseline:
`a21279d6c7313d65eb1239e70f1bae3ae62b1420`. Neither the Python fallback nor
`sync_videos.sh` is used.

For mother x of length M and child y of length N, the September NumPy code used
L=M+N-1 and irfft(rfft(x,L)*conj(rfft(y,L)),L). This represents linear correlation
C(k)=sum_j x[j+k] y[j], with circular storage of negative lags. It searched the
whole array, not +/-120 seconds. The 120-second restriction belonged only to its
Python fallback. The current windowed estimator restricts its coarse searches
to +/-max_lag_seconds (default 120), so a true offset outside that interval cannot
seed the fine search, even when the files have substantial overlap.

Historical RMS normalization divides each entire signal by a constant; it does
not change argmax, compensate changing overlap, remove DC, assess ambiguity or
provide confidence. Global raw sums favor energetic/long overlaps. Also, mapping
indices greater than L//2 to negative lags is incorrect for sufficiently unequal
durations: the actual linear lag range is -(N-1)..M-1, not a symmetric half-array.
The new implementation explicitly uses this linear range via convolution with
reversed child samples, avoiding that historical indexing defect.

For each lag k, use overlap x[a:b], y[a-k:b-k], a=max(0,k), b=min(M,N+k).
Compute Pearson NCC using overlap-local sums, squared sums and C(k):
numerator=C(k)-Sx*Sy/n; denominator=sqrt((Qx-Sx²/n)*(Qy-Sy²/n)). Prefix sums
provide the energy/mean terms. Reject insufficient overlap and near-zero variance;
clip numerical roundoff to [-1,1]. Whole-file DC centering before FFT improves
conditioning without changing this overlap-centered correlation. No downsampling
or lossy decimation is introduced.

Positive k means the same event is later in the mother file: trim the mother by
k/rate. Negative k trims the child. Container offset adds
mom_audio_start-child_audio_start exactly once; candidate alignment uses audio
sample time. The existing trim_plan is unchanged.

Global peaks are **proposals only**. Validate a bounded set with disjoint windows
distributed over each candidate's overlap. Local NCC, peak/competitor ratio,
minimum window count, consensus tolerance and agreeing fraction all apply.
Two distinct validated offsets cause rejection, not winner selection by global
height. No global maximum alone establishes success or scientific QC.

The mode is opt-in via sync.global_fft_enabled; default windowed behavior remains
available. No pipeline, job or pilot is enabled by changing this source code.

## Operational limits and provenance

Parameters: `global_fft_enabled=false`, `global_fft_memory_mb=512` (1..4096 MiB),
`global_fft_candidates=3` (2..8). The full arrays stay mapped at the caller; the
global phase converts to float64 only after preflight. Admission estimate is
192*next_fast_len(M+N-1)+64*(M+N) bytes. A separate conservative validation-window
estimate must also fit. Global workspace is released before window validation.
This is an allocation admission budget, **not** an OS-enforced RSS ceiling: Python,
SciPy, caller-owned arrays and FFT backend allocator overhead also consume RAM.
Budget exhaustion returns LOW_CONFIDENCE, never a truncated or lower-rate result.

At 8 kHz, 512 MiB admits roughly 262 seconds of combined input before FFT padding;
longer recordings need a reviewed larger budget or are blocked. Maximum configured
budget is 4 GiB. There is no claim that full-length field recordings fit, nor an
automatic increase in memory allowance. Existing worker timeouts remain unchanged.
No candidate resampling/decimation is used, so capture delays retain sample-level
resolution before local parabolic interpolation.

The added sync parameters are recorded by existing configuration serialization;
parameter-bound job fingerprints therefore change conservatively. Old approvals
are not silently reused or migrated. Delivery v2 schemas, manifest validators,
storage implementation and scientific QC are unchanged.

Eligible overlap must cover min_agreeing_windows*window_seconds plus both fine
search margins and min_overlap_seconds. Require at least three disjoint windows;
limits allow 3..32 validation windows, window <=600 s, fine search <=60 s,
sample rate <=48 kHz. Silence and nonfinite inputs are rejected. Candidate peak
suppression uses twice the fine-search width. The candidate count is bounded:
strong interference can hide the true alignment outside the proposed peaks,
causing false negatives. Periodicity, drift and nonstationary acoustic conditions
remain scientific limitations; NCC and confidence are not calibrated probabilities.

`SyncEstimate.global_candidates` records audio-domain candidate offsets, global
NCC, overlap, estimated allocation and independent validation outcome. Accepted
result metrics remain window-derived; the container correction is applied only to
the returned estimate. Scientific QC remains external and untouched.

## Regression reference and scope

`tests/test_global_fft.py` reproduces the September NumPy RMS/FFT/argmax formula
as a mathematical oracle, including its half-array defect for highly asymmetric
durations. It covers +/-180 and +/-135.25 seconds, asymmetric +/-350-second lags,
unrelated/silent PCM, repeated ambiguous content, DC/gain changes, insufficient
overlap, memory preflight before allocation, unchanged mapped sources, deterministic
results and container stream timestamps. One long-offset test uses the standard
8 kHz analysis rate; other mathematical cases use 400 Hz generated PCM for bounded
CI cost. Existing tests/test_legacy_audit.py preserves the historical sign/trim
regressions. No historical shell command, fallback Python or real video is run.

Run `python -m pytest -ra tests/test_global_fft.py tests/test_syncest.py
tests/test_legacy_audit.py` and the complete suite. This is synthetic validation,
not a conclusion about pilot P3. P3 requires separately authorized input access,
measured resource fit and review of candidate/window evidence and scientific QC.
