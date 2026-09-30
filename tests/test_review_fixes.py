"""Regression tests for the review findings on PR #1 (each was reproduced before being fixed)."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import numpy as np
import pytest

from helpers import recording, wall_signal
from rg2019 import config as cfgmod, media
from rg2019.config import SyncParams
from rg2019.pipeline import Pipeline
from rg2019.state import RunLock, StateStore
from rg2019.statuses import S
from rg2019.syncest import estimate_offset

PID = "ID100392"


def run(cfg, **kw):
    return Pipeline(cfg, **kw).run()


def state(cfg, pid=PID):
    return json.loads(StateStore(cfg).path(pid).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- P1: recheck must see NEW files
def test_file_arriving_during_the_recheck_blocks_processing(cfg, make_participant):
    cfg.stability_minutes, cfg.stability_recheck_seconds = 0, 1
    d = make_participant(PID)

    def new_file_arrives(_):
        (d / "late_arrival_mom_2.mp4").write_bytes(b"synology is still writing this")
    s = Pipeline(cfg, sleep_fn=new_file_arrives).run()
    assert s.waiting == [PID] and "changed during" in state(cfg)["message"]
    assert not (cfg.raw_dir / PID).exists()


def test_file_disappearing_during_the_recheck_also_blocks(cfg, make_participant):
    cfg.stability_minutes, cfg.stability_recheck_seconds = 0, 1
    d = make_participant(PID)
    (d / "notes.txt").write_text("x")
    s = Pipeline(cfg, sleep_fn=lambda _: (d / "notes.txt").unlink()).run()
    assert s.waiting == [PID] and not (cfg.raw_dir / PID).exists()


# ---------------------------------------------------------------- P1: lock must not be stolen from a live run
def test_lock_held_by_a_live_run_is_not_taken_over_even_after_stale_hours(tmp_path):
    lock_path = tmp_path / "pipeline.lock"
    stale_hours = 3 / 3600                      # "stale" after 3 s so the test is quick
    first = RunLock(lock_path, stale_hours)
    first.acquire()
    try:
        time.sleep(4.5)                         # longer than stale_hours: an age-only rule would now steal it
        with pytest.raises(RuntimeError, match="another pipeline run"):
            RunLock(lock_path, stale_hours).acquire()
        assert lock_path.exists()
    finally:
        first.release()
    assert not lock_path.exists()


def test_lock_of_a_crashed_run_is_recovered_after_stale_hours(tmp_path):
    lock_path = tmp_path / "pipeline.lock"
    lock_path.write_text("pid=999999 (crashed, no heartbeat)")
    old = time.time() - 48 * 3600
    os.utime(lock_path, (old, old))
    lk = RunLock(lock_path, 24)
    lk.acquire()
    assert lk.held and f"pid={os.getpid()}" in lock_path.read_text()
    lk.release()


def test_fresh_foreign_lock_is_respected(tmp_path):
    lock_path = tmp_path / "pipeline.lock"
    lock_path.write_text("pid=1")
    with pytest.raises(RuntimeError):
        RunLock(lock_path, 24).acquire()
    assert lock_path.exists()


def test_heartbeat_thread_stops_on_release(tmp_path):
    import threading
    before = threading.active_count()
    lk = RunLock(tmp_path / "l.lock", 1)
    lk.acquire()
    assert threading.active_count() == before + 1
    lk.release()
    time.sleep(0.3)
    assert threading.active_count() == before


# ---------------------------------------------------------------- P2: side-by-side is validated when expected
def test_deleted_side_by_side_is_regenerated_not_reported_success_forever(cfg, make_participant):
    cfg.create_side_by_side = True
    make_participant(PID)
    assert run(cfg).newly_completed == [PID]
    out = cfg.synced_dir / PID
    sbs, mom = out / f"{PID}_side_by_side.mp4", out / f"{PID}_mom_synced.mp4"
    mom_mtime = mom.stat().st_mtime_ns
    sbs.unlink()
    s = run(cfg)
    assert s.newly_completed == [PID] and sbs.is_file()           # recreated, not silently "skipped"
    assert mom.stat().st_mtime_ns == mom_mtime                    # the good outputs were not re-encoded
    assert run(cfg).skipped_completed == [PID]                    # and now it is stable again


def test_truncated_side_by_side_is_flagged_and_never_overwritten(cfg, make_participant):
    cfg.create_side_by_side = True
    make_participant(PID)
    run(cfg)
    sbs = cfg.synced_dir / PID / f"{PID}_side_by_side.mp4"
    sbs.write_bytes(sbs.read_bytes()[:1000])
    s = run(cfg)
    assert s.manual_review == [PID] and state(cfg)["status"] == S.OUTPUT_CONFLICT
    assert sbs.stat().st_size == 1000


def test_side_by_side_not_expected_is_not_required_or_retro_generated(cfg, make_participant):
    make_participant(PID)                                          # created while disabled
    run(cfg)
    cfg.create_side_by_side = True                                 # enabled later
    assert run(cfg).skipped_completed == [PID]
    assert not (cfg.synced_dir / PID / f"{PID}_side_by_side.mp4").exists()


# ---------------------------------------------------------------- P1: distinct fine windows only
R = 8000
PRM = SyncParams(max_lag_seconds=30, window_seconds=20)


def pcm(x):
    return (np.clip(x, -1, 1) * 32000).astype("<i2")


def test_overlap_no_longer_than_one_window_cannot_reach_consensus_from_duplicates():
    """Stage 1 succeeds (coarse offset found) but the aligned overlap (25 s) is barely longer than one
    20 s window, so all fine windows would start at (almost) the same place."""
    wall = wall_signal(120, R, seed=5)
    mom = pcm(recording(wall, R, 0, 60))
    child = pcm(recording(wall, R, 10, 25))        # perfect copy
    est = estimate_offset(mom, child, PRM)
    assert est.coarse_offset_seconds == pytest.approx(10.0, abs=0.01)     # stage 1 did work
    assert not est.ok                                # one clear peak must NOT satisfy "3 agreeing windows"
    fine = [w for w in est.windows if w.stage == 2]
    assert len(fine) == est.n_windows == 1 and est.n_agree <= 1
    assert "distinct" in est.reason


def test_fine_windows_are_distinct_and_spaced_at_least_half_a_window_apart():
    wall = wall_signal(200, R, seed=5)
    est = estimate_offset(pcm(recording(wall, R, 0, 120)), pcm(recording(wall, R, 5, 100)), PRM)
    assert est.ok
    pos = sorted(w.position_seconds for w in est.windows if w.stage == 2)
    assert len(pos) == len(set(pos)) >= PRM.min_agreeing_windows
    assert all(b - a >= PRM.window_seconds / 2 - 1e-6 for a, b in zip(pos, pos[1:]))


def test_config_rejects_min_agreeing_windows_above_fine_windows(tmp_path):
    with pytest.raises(cfgmod.ConfigError, match="min_agreeing_windows"):
        cfgmod.from_dict({"followup_root": str(tmp_path), "sync": {"fine_windows": 2, "min_agreeing_windows": 3}})


def test_fine_windows_at_the_overlap_edges_are_fully_inside_both_files():
    """Regression for the edge effect exposed while fixing window distinctness: with a 150 s mother and a
    45 s child (offset 12 s) every distinct fine window must be valid, including the first and last."""
    wall = wall_signal(200, R, seed=5)
    est = estimate_offset(pcm(recording(wall, R, 0, 150)), pcm(recording(wall, R, 12, 45)), PRM)
    fine = [w for w in est.windows if w.stage == 2]
    assert est.ok and len(fine) >= 3 and all(w.valid for w in fine)
    assert est.n_agree == est.n_windows
