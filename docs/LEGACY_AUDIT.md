# Audit of the legacy Bash scripts

Scope: `sync_research_project.sh` (batch) and `sync_videos.sh` (two files). Both are kept
unchanged (apart from a LEGACY comment banner) for historical reference.
Every finding below is reproduced by `tests/test_legacy_audit.py`, which extracts the **actual**
Python heredocs from the scripts and runs them on synthetic audio with known offsets.

## Vocabulary

Camera *A* "starts later by D" means its recording began D seconds after camera *B*'s. The camera
that started **earlier** holds D seconds of extra material at the start of its file, so **that
earlier camera is the one to trim**, by D, so both files begin at the same real-world event.

## Finding 1 - offset sign / trimming

`corr = irfft(rfft(a) * conj(rfft(b)))` gives `corr[k] = sum_t a[t+k] * b[t]`. With `a = mom`,
`b = child`, a peak at `k > 0` means `mom[t+k] == child[t]`: the event is `k` samples *later* in the
mother file, so the mother camera started earlier and **mom must be trimmed**.

| Code path | Result of the test (5 s / 20 s, both signs, and zero) |
|---|---|
| `sync_research_project.sh`, numpy FFT path (normal path) | **Correct.** offset = child_start - mom_start; `offset > 0` trims mom; `offset < 0` trims child. All 5 cases pass. (The earlier suspicion of an inverted sign in this path is **not** confirmed.) |
| `sync_videos.sh` | **Bug confirmed.** The estimator uses the same convention as above (`+` = video1 has the lead-in) but the export trims **video2** for `offset >= 0` and **video1** otherwise - the wrong camera in every non-zero case. Outputs would start 2x|offset| seconds apart. |
| `sync_research_project.sh`, pure-Python fallback (only when `import numpy` fails) | **Unreliable.** Returns 35, 45, 60 and 40 s for true offsets of 5, -5, -20 and 0 s (un-normalised dot product, mismatched window bookkeeping). It is a silent-failure path: a machine without numpy would produce wrong syncs with no warning. |

Other algorithmic weaknesses (not sign bugs): the numpy path runs one FFT over the *entire* audio
(RAM grows with recording length), has no confidence measure (`argmax` is always "a result"), and
`sync_videos.sh` searches only the first 60 s with a pure-Python O(lags x window) loop.

## Finding 2 - `set -e` and `((COUNTER++))`

`sync_research_project.sh` has `set -e` and increments `PROCESSED`, `SKIPPED` and `FAILED` (all initialised to `0`) with `((X++))`.
In Bash the *post*-increment expression evaluates to the **old** value; an arithmetic command
whose value is 0 returns exit status 1; under `set -e` a non-zero status aborts the script.
Reproduced: `bash -c 'set -e; N=0; ((N++)); echo REACHED'` exits with status 1 and never prints.

**Consequence:** the script exits at the first `((SKIPPED++))` / `((FAILED++))`, i.e. at the very first
participant that is skipped or fails, and after the first *successful* participant it exits at
`((PROCESSED++))` - after the `.sync_done` marker and report row are written but before the temp
directory is removed, the summary is printed and the notification is shown. So a batch handles at most
one participant per run. (`X=$((X+1))` or `((++X))` are safe.) The abort was demonstrated on the
isolated construct (test above) and follows from the script's code; the full script was not run on real data.
This cannot affect v2 (Python), but it is why v2 isolates every participant in `try/except`.

## Other reasons the legacy scripts are unsuitable for the NAS workflow

* Write `.sync_done`, `synced/` and the report **inside the participant folder** (would pollute `01_RAW`).
* Silently take the first `find ... | head -1` match; no ambiguity handling.
* No validation (ffprobe), no checksums, no readiness/stability check for Synology Drive.
* Always create the (large) side-by-side file; `-y` overwrites outputs; no `.partial`/atomic rename.
* `sync_report.csv` is append-only, so re-runs duplicate rows; macOS `osascript` notifications.
