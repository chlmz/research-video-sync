"""Hardening pass: transfer-file safety, dry-run/prior-observation, RAW integrity, stray JSON."""
from __future__ import annotations

import csv
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

import pytest

import pipeline_rg2019 as cli
from rg2019 import media
from rg2019 import pipeline as pl
from rg2019.pipeline import Pipeline
from rg2019.state import SCHEMA, StateStore
from rg2019.statuses import S

PID = "ID100392"


def run(cfg, **kw):
    return Pipeline(cfg, **kw).run()


def state(cfg, pid=PID):
    return json.loads(StateStore(cfg).path(pid).read_text(encoding="utf-8"))


def tree(root: Path):
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file()}


def age_files(folder: Path, seconds: float = 86400):
    old = datetime.now().timestamp() - seconds
    for f in folder.rglob("*"):
        if f.is_file():
            os.utime(f, (old, old))


# =================================================================== 1. transfer files always block
TRANSIT_NAMES = [f"{PID}_child.mp4.partial", f"{PID}_child.mp4.tmp", f"{PID}_child.mp4.part",
                 f"{PID}_child.mp4.crdownload", f"{PID}_child.mp4.download", f"{PID}_child.mp4.filepart",
                 f".~{PID}_child.mp4", f"~${PID}_notes.tmp"]


@pytest.mark.parametrize("transit", TRANSIT_NAMES)
def test_transfer_file_blocks_even_when_stability_minutes_is_zero(cfg, make_participant, transit):
    assert cfg.stability_minutes == 0
    d = make_participant(PID)
    (d / transit).write_bytes(b"still downloading")
    before_inbox = tree(cfg.inbox_dir)
    s = run(cfg)
    assert s.waiting == [PID] and not s.newly_completed
    assert state(cfg)["status"] == S.WAITING_FOR_STABILITY
    assert "transfer-in-progress" in state(cfg)["message"]
    assert not (cfg.raw_dir / PID).exists()                       # nothing moved into RAW
    assert not (cfg.synced_dir / PID).exists()
    assert tree(cfg.inbox_dir) == before_inbox                    # INBOX untouched


def test_partial_and_tmp_together_and_nested_are_blocked_and_nothing_is_moved(cfg, make_participant):
    d = make_participant(PID)
    (d / "sub").mkdir()
    (d / "sub" / "x.mp4.partial").write_bytes(b"x")
    (d / "y.tmp").write_bytes(b"y")
    s = run(cfg)
    assert s.waiting == [PID] and not list(cfg.raw_dir.iterdir())


def test_processing_resumes_once_the_transfer_file_is_gone(cfg, make_participant):
    d = make_participant(PID)
    tmpf = d / f"{PID}_child.mp4.partial"
    tmpf.write_bytes(b"x")
    assert run(cfg).waiting == [PID]
    tmpf.unlink()                                                 # transfer finished (renamed away)
    assert run(cfg).newly_completed == [PID]


def test_transfer_file_also_blocks_in_dry_run_and_with_positive_stability(cfg, make_participant):
    d = make_participant(PID)
    (d / f"{PID}_mom.mp4.tmp").write_bytes(b"x")
    assert run(cfg, dry_run=True).waiting == [PID]
    cfg.stability_minutes = 5
    age_files(d)
    assert run(cfg).waiting == [PID]


def test_recheck_stays_active_when_stability_minutes_is_zero(cfg, make_participant):
    """Chosen behaviour: stability_minutes=0 disables only the age/prior-observation rules; the short
    growth re-check is governed solely by stability_recheck_seconds (safer default)."""
    cfg.stability_minutes = 0
    cfg.stability_recheck_seconds = 1
    d = make_participant(PID)

    def growing(_):
        with open(d / f"{PID}_mom.mp4", "ab") as fh:
            fh.write(b"\0")
    s = Pipeline(cfg, sleep_fn=growing).run()
    assert s.waiting == [PID] and "changed during" in state(cfg)["message"]
    assert not (cfg.raw_dir / PID).exists()


def test_recheck_can_be_disabled_explicitly(cfg, make_participant):
    cfg.stability_minutes, cfg.stability_recheck_seconds = 0, 0
    make_participant(PID)
    assert run(cfg, sleep_fn=lambda s: pytest.fail("must not sleep")).newly_completed == [PID]


# =================================================================== 2. dry-run + prior observation
def _prior_obs_cfg(cfg):
    cfg.stability_minutes = 10
    cfg.stability_requires_prior_observation = True
    cfg.stability_recheck_seconds = 0


def test_dry_run_warns_about_prior_observation_and_stays_fully_non_mutating(cfg, make_participant, caplog):
    _prior_obs_cfg(cfg)
    d = make_participant(PID)
    age_files(d)
    snapshot = tree(cfg.followup_root)
    dirs = sorted(str(p.relative_to(cfg.followup_root)) for p in cfg.followup_root.rglob("*"))
    with caplog.at_level(logging.WARNING, logger="rg2019"):
        s1 = run(cfg, dry_run=True)
        s2 = run(cfg, dry_run=True)                               # repeating does not help: no state
    assert s1.waiting == s2.waiting == [PID] and not s1.would_process
    assert "first observation" in next(o for o in s1.outcomes).message
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
                and "dry-run cannot record the stability observation timer" in r.getMessage()]
    assert len(warnings) == 2
    assert "stability_requires_prior_observation=false" in warnings[0] and "TEMPORARILY" in warnings[0]
    assert any("NOTE:" in line and "stability_requires_prior_observation" in line
               for line in s1.render().splitlines())
    # nothing changed anywhere: same files, sizes, mtimes, same directories, no state/CSV/log
    assert tree(cfg.followup_root) == snapshot
    assert sorted(str(p.relative_to(cfg.followup_root)) for p in cfg.followup_root.rglob("*")) == dirs
    assert not cfg.state_dir.exists() and not cfg.status_csv.exists() and not cfg.log_file_dir.exists()


def test_dry_run_with_prior_observation_disabled_does_the_full_pilot_without_mutating(
        cfg, make_participant, caplog):
    _prior_obs_cfg(cfg)
    cfg.stability_requires_prior_observation = False              # the documented temporary pilot setting
    d = make_participant(PID)
    age_files(d)
    snapshot = tree(cfg.followup_root)
    with caplog.at_level(logging.WARNING, logger="rg2019"):
        s = run(cfg, dry_run=True)
    assert s.would_process == [PID] and not s.notes
    assert not any("dry-run cannot record" in r.getMessage() for r in caplog.records)
    assert tree(cfg.followup_root) == snapshot and not cfg.state_dir.exists()


def test_no_warning_when_stability_is_off_or_not_a_dry_run(cfg, make_participant, caplog):
    make_participant(PID)
    with caplog.at_level(logging.WARNING, logger="rg2019"):
        run(cfg, dry_run=True)                                    # stability_minutes == 0
        cfg.stability_minutes = 10
        run(cfg)                                                  # real run
    assert not any("dry-run cannot record" in r.getMessage() for r in caplog.records)


def test_cli_dry_run_prints_the_warning_and_changes_nothing(cfg, make_participant, project, tmp_path, capsys):
    d = make_participant(PID)
    age_files(d)
    conf = tmp_path / "config.json"
    conf.write_text(json.dumps({"followup_root": str(project), "stability_minutes": 10,
                                "stability_recheck_seconds": 0}), encoding="utf-8")
    before = tree(project)
    code = cli.main(["--config", str(conf), "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0 and tree(project) == before
    assert "dry-run cannot record the stability observation timer" in out
    assert "stability_requires_prior_observation=false" in out


# =================================================================== 3. RAW integrity
@pytest.fixture
def done(cfg, make_participant):
    make_participant(PID)
    assert run(cfg).newly_completed == [PID]
    return cfg.raw_dir / PID


@pytest.fixture
def sha_calls(monkeypatch):
    calls = []
    real = media.sha256_file
    monkeypatch.setattr(media, "sha256_file", lambda p, *a, **k: calls.append(Path(p).name) or real(p, *a, **k))
    return calls


def test_A_unchanged_raw_is_never_rehashed(cfg, done, sha_calls):
    for _ in range(5):
        assert run(cfg).skipped_completed == [PID]
    assert sha_calls == []


def test_B_same_size_modified_content_is_raw_conflict(cfg, done, sha_calls):
    f = done / f"{PID}_mom.mp4"
    data = bytearray(f.read_bytes())
    data[len(data) // 2] ^= 0xFF                                  # flip one byte, size unchanged
    f.write_bytes(bytes(data))
    size = f.stat().st_size
    tampered = (f.stat().st_size, f.stat().st_mtime_ns, f.read_bytes())
    outputs = tree(cfg.synced_dir)
    s = run(cfg)
    assert s.manual_review == [PID] and state(cfg)["status"] == S.RAW_CONFLICT
    assert "SHA-256" in state(cfg)["message"] and f.stat().st_size == size
    assert sha_calls == [f.name]                                  # hashed exactly once, only the changed file
    assert (f.stat().st_size, f.stat().st_mtime_ns, f.read_bytes()) == tampered   # RAW never modified by us
    assert tree(cfg.synced_dir) == outputs                        # no reprocessing
    sha_calls.clear()
    assert run(cfg).manual_review == [PID]                        # stays flagged on later runs
    assert len(sha_calls) <= 1


def test_B2_size_change_is_immediate_conflict_without_hashing(cfg, done, sha_calls):
    f = done / f"{PID}_child.mp4"
    f.write_bytes(f.read_bytes() + b"x")
    assert run(cfg).manual_review == [PID] and state(cfg)["status"] == S.RAW_CONFLICT
    assert "size differs" in state(cfg)["message"] and sha_calls == []


def test_C_mtime_only_change_hashes_once_stays_valid_and_updates_state_only(cfg, done, sha_calls):
    f = done / f"{PID}_mom.mp4"
    before_bytes = f.read_bytes()
    old_state_mtime = state(cfg)["sources"]["mom"]["mtime_ns"]
    new = datetime.now().timestamp() + 1000
    os.utime(f, (new, new))                                       # "touch": same content, new mtime
    touched = f.stat().st_mtime_ns
    assert touched != old_state_mtime

    s = run(cfg)
    assert s.skipped_completed == [PID] and state(cfg)["status"] == S.SUCCESS
    assert sha_calls == [f.name]                                  # exactly one hash, of the touched file only
    assert state(cfg)["sources"]["mom"]["mtime_ns"] == touched    # STATE updated ...
    assert f.stat().st_mtime_ns == touched and f.read_bytes() == before_bytes   # ... RAW untouched
    for _ in range(3):                                            # and it does not keep rehashing
        assert run(cfg).skipped_completed == [PID]
    assert sha_calls == [f.name]


def test_C2_mtime_change_on_both_sources_hashes_each_once(cfg, done, sha_calls):
    new = datetime.now().timestamp() + 500
    for f in done.iterdir():
        os.utime(f, (new, new))
    assert run(cfg).skipped_completed == [PID]
    assert sorted(sha_calls) == [f"{PID}_child.mp4", f"{PID}_mom.mp4"]
    run(cfg)
    assert len(sha_calls) == 2


def test_C3_dry_run_verifies_but_persists_nothing(cfg, done, sha_calls):
    f = done / f"{PID}_mom.mp4"
    new = datetime.now().timestamp() + 1000
    os.utime(f, (new, new))
    state_bytes = StateStore(cfg).path(PID).read_bytes()
    everything = tree(cfg.followup_root)
    s = run(cfg, dry_run=True)
    assert s.skipped_completed == [PID]
    assert StateStore(cfg).path(PID).read_bytes() == state_bytes and tree(cfg.followup_root) == everything


def test_documented_limit_edit_preserving_size_and_mtime_is_not_detected_daily(cfg, done, sha_calls):
    """Honest limit (README): without hashing every run, an edit that preserves BOTH size and mtime cannot
    be seen by the daily check.  The stored SHA-256 exists for manual audit."""
    f = done / f"{PID}_mom.mp4"
    st = f.stat()
    data = bytearray(f.read_bytes())
    data[100] ^= 0xFF
    f.write_bytes(bytes(data))
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert run(cfg).skipped_completed == [PID] and sha_calls == []
    assert media.sha256_file(f) != state(cfg)["sources"]["mom"]["sha256"]     # the audit trail still catches it


# =================================================================== 4. stray JSON / CSV
def test_stray_json_never_reaches_the_csv(cfg, make_participant):
    make_participant(PID)
    cfg.state_dir.mkdir(parents=True)
    (cfg.state_dir / "notes.json").write_text(json.dumps({"participant_id": "ID555555", "schema": SCHEMA,
                                                          "status": "SUCCESS"}))
    s = run(cfg)
    assert s.newly_completed == [PID] and (cfg.state_dir / "notes.json").exists()
    rows = list(csv.DictReader(cfg.status_csv.open(encoding="utf-8", newline="")))
    assert [r["participant_id"] for r in rows] == [PID]
    assert "notes" not in cfg.status_csv.read_text(encoding="utf-8")


def test_rewrite_csv_only_emits_genuine_state_records(cfg):
    store = StateStore(cfg)
    cfg.state_dir.mkdir(parents=True)
    good = {"schema": SCHEMA, "participant_id": "ID100001", "status": S.SUCCESS, "sources": {}, "sync": {}}
    files = {
        "ID100001.json": good,                                                             # genuine
        "notes.json": {"participant_id": "ID100002", "schema": SCHEMA, "status": "SUCCESS"},   # invalid file name
        "ID100003.json": {**good, "participant_id": "ID999999"},                           # id != file name
        "ID100004.json": {"participant_id": "ID100004", "status": "SUCCESS"},              # no schema marker
        "ID100005.json": {"schema": SCHEMA, "status": "SUCCESS"},                          # no participant_id
        "ID100006.json": ["not", "an", "object"],                                          # wrong JSON type
        "ID100007.json": {**good, "participant_id": "ID100007", "schema": 999},            # foreign schema
        "IDxyz.json": {**good, "participant_id": "IDxyz"},                                 # fails configured id rule
    }
    for name, content in files.items():
        (cfg.state_dir / name).write_text(json.dumps(content))
    (cfg.state_dir / "ID100008.json").write_text("{ broken json")
    store.rewrite_csv()
    rows = list(csv.DictReader(cfg.status_csv.open(encoding="utf-8", newline="")))
    assert [r["participant_id"] for r in rows] == ["ID100001"]
    # every file whose NAME is a valid id is a candidate; only genuine records reach the CSV
    assert store.all_ids() == ["ID100001", "ID100003", "ID100004", "ID100005", "ID100006", "ID100007", "ID100008"]


def test_all_ids_ignores_names_that_are_not_participant_ids(cfg):
    cfg.state_dir.mkdir(parents=True)
    for n in ("notes.json", "config.json", "ID100001.json", "id100002.json", "ID1.json"):
        (cfg.state_dir / n).write_text("{}")
    assert StateStore(cfg).all_ids() == ["ID100001"]
