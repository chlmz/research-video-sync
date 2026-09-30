"""Sync estimator + sign convention (tests 7,8,9,10).

Truth model: mom camera starts at wall-time ms, child camera at cs; both record the same
sound.  offset_seconds must equal  t_mom(event) - t_child(event) = cs - ms.
The camera that started EARLIER holds the extra lead-in and is the one that must be trimmed."""
from __future__ import annotations

import numpy as np
import pytest

from helpers import recording, wall_signal
from rg2019.config import SyncParams
from rg2019.syncest import estimate_offset, trim_plan

R = 8000
PRM = SyncParams(max_lag_seconds=30, window_seconds=20)


def pcm(x):
    return (np.clip(x, -1, 1) * 32000).astype("<i2")


@pytest.fixture(scope="module")
def wall():
    return wall_signal(200, R, seed=5)


CASES = [
    # label, mom_start, child_start, expected offset, who must be trimmed
    ("child starts 5s later  (child delayed +5)", 0, 5, +5.0, "mom"),
    ("child starts 20s later (child delayed +20)", 0, 20, +20.0, "mom"),
    ("mom starts 5s later    (mother delayed +5)", 5, 0, -5.0, "child"),
    ("mom starts 20s later   (mother delayed +20)", 20, 0, -20.0, "child"),
    ("zero offset", 0, 0, 0.0, "none"),
]


@pytest.mark.parametrize("label,ms,cs,expected,trimmed", CASES, ids=[c[0].split("(")[0].strip() for c in CASES])
def test_known_offsets_and_correct_camera_is_trimmed(wall, label, ms, cs, expected, trimmed):
    mom, child = pcm(recording(wall, R, ms, 120)), pcm(recording(wall, R, cs, 100))
    est = estimate_offset(mom, child, PRM)
    assert est.ok, est.reason
    assert est.offset_seconds == pytest.approx(expected, abs=0.005)
    assert est.confidence > 0.5

    mt, ct = trim_plan(est.offset_seconds, min_trim=0.001)
    who = "mom" if mt > 0 else "child" if ct > 0 else "none"
    assert who == trimmed
    # the trimmed camera is exactly the one that started earlier
    earlier = "mom" if ms < cs else "child" if cs < ms else "none"
    assert who == earlier
    assert (mt or ct) == pytest.approx(abs(cs - ms), abs=0.005)

    # ...and after trimming both signals start at the same real-world instant:
    a = np.asarray(mom, float)[int(round(mt * R)):]
    b = np.asarray(child, float)[int(round(ct * R)):]
    n = min(a.size, b.size)
    a, b = a[:n], b[:n]
    assert np.corrcoef(a, b)[0, 1] > 0.999
    # whereas trimming the WRONG camera would destroy the alignment
    if who != "none":
        wa = np.asarray(mom, float)[int(round(ct * R)):]
        wb = np.asarray(child, float)[int(round(mt * R)):]
        m = min(wa.size, wb.size)
        assert abs(np.corrcoef(wa[:m], wb[:m])[0, 1]) < 0.1


def test_mathematical_derivation_of_the_sign_with_the_legacy_fft_formula(wall):
    """corr = irfft(rfft(a) * conj(rfft(b))) gives corr[k] = sum_t a[t+k] b[t].  If a=mom and b=child,
    the peak lag k is where mom[t+k] == child[t]: the event is k samples LATER in mom, i.e. the mom
    camera started k samples EARLIER, i.e. offset = +k/R and mom must be trimmed."""
    mom = recording(wall, R, 0, 60)      # mom started first
    child = recording(wall, R, 7, 40)    # child started 7 s later
    n = mom.size + child.size - 1
    corr = np.fft.irfft(np.fft.rfft(mom, n) * np.conj(np.fft.rfft(child, n)), n)
    lag = int(np.argmax(corr))
    lag = lag - n if lag > n // 2 else lag
    assert lag == 7 * R                                     # positive lag <=> mom has the lead-in
    assert estimate_offset(pcm(mom), pcm(child), PRM).offset_seconds == pytest.approx(lag / R, abs=0.005)


def test_trim_plan_convention():
    assert trim_plan(+3.5) == (3.5, 0.0)      # positive -> trim MOM
    assert trim_plan(-3.5) == (0.0, 3.5)      # negative -> trim CHILD
    assert trim_plan(0.0) == (0.0, 0.0)
    assert trim_plan(0.01, min_trim=0.02) == (0.0, 0.0)


def test_different_durations_and_child_much_shorter(wall):
    est = estimate_offset(pcm(recording(wall, R, 0, 150)), pcm(recording(wall, R, 12, 45)), PRM)
    assert est.ok and est.offset_seconds == pytest.approx(12.0, abs=0.005)


def test_tolerates_strong_independent_noise_in_one_channel(wall):
    rng = np.random.default_rng(0)
    m = recording(wall, R, 0, 100)
    c = recording(wall, R, 6, 100)
    c = c + rng.standard_normal(c.size).astype(np.float32) * (np.std(c) * 1.0)   # ~0 dB SNR
    est = estimate_offset(pcm(m), pcm(c / np.max(np.abs(c))), PRM)
    assert est.ok and est.offset_seconds == pytest.approx(6.0, abs=0.01)


def test_unrelated_noise_is_low_confidence_not_success():
    rng = np.random.default_rng(1)
    est = estimate_offset(pcm(rng.standard_normal(R * 100) * 0.1), pcm(rng.standard_normal(R * 100) * 0.1), PRM)
    assert not est.ok
    assert "no coarse consensus" in est.reason or "windows" in est.reason


def test_unrelated_speechlike_signals_are_low_confidence():
    a = wall_signal(100, R, seed=100)
    b = wall_signal(100, R, seed=200)
    est = estimate_offset(pcm(a), pcm(b), PRM)
    assert not est.ok


def test_silent_child_is_low_confidence(wall):
    est = estimate_offset(pcm(recording(wall, R, 0, 100)), np.zeros(R * 100, "<i2"), PRM)
    assert not est.ok


def test_offset_beyond_max_lag_is_low_confidence_not_a_wrong_success(wall):
    mom, child = pcm(recording(wall, R, 0, 120)), pcm(recording(wall, R, 50, 100))
    est = estimate_offset(mom, child, PRM)                     # true offset +50 s, search only +-30 s
    assert not est.ok


def test_too_short_audio_is_low_confidence():
    x = pcm(wall_signal(3, R, seed=1))
    assert not estimate_offset(x, x, PRM).ok


def test_deterministic_and_memmap_input(tmp_path, wall):
    m, c = pcm(recording(wall, R, 0, 100)), pcm(recording(wall, R, 4.25, 100))
    for name, arr in (("m.pcm", m), ("c.pcm", c)):
        arr.tofile(tmp_path / name)
    mm = np.memmap(tmp_path / "m.pcm", dtype="<i2", mode="r")
    cm = np.memmap(tmp_path / "c.pcm", dtype="<i2", mode="r")
    e1, e2 = estimate_offset(mm, cm, PRM), estimate_offset(m, c, PRM)
    assert e1.offset_seconds == e2.offset_seconds == pytest.approx(4.25, abs=0.005)
    assert estimate_offset(mm, cm, PRM).offset_seconds == e1.offset_seconds


def test_audio_stream_start_time_is_folded_into_container_offset(wall):
    """If the child's audio stream starts 0.5 s after its container start, container-time offset
    shifts by -(-0.5)... verified against the definition offset = (t_mom+a_m) - (t_child+a_c)."""
    m, c = pcm(recording(wall, R, 0, 100)), pcm(recording(wall, R, 5, 100))
    base = estimate_offset(m, c, PRM).offset_seconds
    shifted = estimate_offset(m, c, PRM, mom_audio_start=0.0, child_audio_start=0.5).offset_seconds
    assert shifted == pytest.approx(base - 0.5, abs=0.001)


def test_result_reports_quality_metrics(wall):
    est = estimate_offset(pcm(recording(wall, R, 0, 100)), pcm(recording(wall, R, 3, 100)), PRM)
    d = est.to_dict()
    assert {"offset_seconds", "confidence", "n_agree", "n_windows", "median_ncc",
            "offset_spread_seconds", "windows", "reason"} <= set(d)
    assert est.n_agree >= 3 and est.offset_spread_seconds < 0.01
