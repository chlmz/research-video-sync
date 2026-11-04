"""Pairs may share folders or live at the inbox root; paths remain isolated."""
import json
import os
import shutil

from rg2019 import pipeline as pl
from rg2019.config import from_dict
from rg2019.discovery import discover_jobs, video_id
from rg2019.pipeline import Pipeline
from rg2019.state import StateStore
from rg2019.statuses import S


def test_two_pairs_in_same_folder(cfg, video_cache):
    folder = cfg.inbox_dir / "batch"
    folder.mkdir()
    source = video_cache(0, 5)
    for pid in ("ID100392", "ID100534"):
        for role in ("mom", "child"):
            shutil.copy2(source / f"{role}.mp4", folder / f"{pid}_{role}.mp4")

    assert Pipeline(cfg).run().newly_completed == ["ID100392", "ID100534"]
    for pid in ("ID100392", "ID100534"):
        assert (cfg.raw_dir / "batch" / f"{pid}_mom.mp4").is_file()
        assert (cfg.synced_dir / "batch" / f"{pid}_mom_synced.mp4").is_file()
    assert Pipeline(cfg).run().skipped_completed == ["ID100392", "ID100534"]


def test_root_pair_without_subfolders(cfg, video_cache):
    source = video_cache(0, 5)
    for role in ("mom", "child"):
        shutil.copy2(source / f"{role}.mp4", cfg.inbox_dir / f"ID100392_{role}.mp4")
    assert Pipeline(cfg, dry_run=True).run().would_process == ["ID100392"]
    assert Pipeline(cfg).run().newly_completed == ["ID100392"]
    assert (cfg.raw_dir / "ID100392_mom.mp4").is_file()
    assert (cfg.synced_dir / "ID100392_child_synced.mp4").is_file()


def test_id_falls_back_to_path_and_preserves_nested_path(cfg, video_cache):
    folder = cfg.inbox_dir / "wave" / "ID100392" / "camera"
    folder.mkdir(parents=True)
    source = video_cache(0, 5)
    for role in ("mom", "child"):
        shutil.copy2(source / f"{role}.mp4", folder / f"session_{role}.mp4")
    assert Pipeline(cfg).run().newly_completed == ["ID100392"]
    assert (cfg.raw_dir / "wave" / "ID100392" / "camera" / "session_mom.mp4").is_file()
    assert (cfg.synced_dir / "wave" / "ID100392" / "camera" /
            "ID100392_mom_synced.mp4").is_file()


def test_cross_folder_pair_is_not_accepted(cfg, video_cache):
    source = video_cache(0, 5)
    for role in ("mom", "child"):
        folder = cfg.inbox_dir / role
        folder.mkdir()
        shutil.copy2(source / f"{role}.mp4", folder / f"ID100392_{role}.mp4")
    assert discover_jobs(cfg, cfg.inbox_dir)["ID100392"].problem == "AMBIGUOUS"
    assert Pipeline(cfg).run().manual_review == ["ID100392"]
    assert json.loads(StateStore(cfg).path("ID100392").read_text())["status"] == S.AMBIGUOUS_FILES
    assert not list(cfg.raw_dir.rglob("*.mp4"))


def test_filename_id_takes_priority_over_directory_and_hash_ids(tmp_path):
    cfg = from_dict({"followup_root": str(tmp_path), "participant_id_regex": r"^#\d{4,8}$"})
    root = tmp_path / "00_INBOX"
    path = root / "#100001" / "#100002_mom.mp4"
    path.parent.mkdir(parents=True)
    path.touch()
    assert video_id(cfg, path, root) == "#100002"
    assert video_id(cfg, path.with_name("session_mom.mp4"), root) == "#100001"
    assert video_id(cfg, path.with_name("session#100002mom.mp4"), root) == "#100002"


def test_more_than_two_matching_videos_rejected(cfg, video_cache):
    source = video_cache(0, 5)
    for role in ("mom", "child"):
        shutil.copy2(source / f"{role}.mp4", cfg.inbox_dir / f"ID100392_{role}.mp4")
    shutil.copy2(source / "mom.mp4", cfg.inbox_dir / "ID100392_mom_copy.mp4")
    assert Pipeline(cfg).run().manual_review == ["ID100392"]
    assert not list(cfg.raw_dir.rglob("*.mp4"))


def test_ready_marker_required_at_root(cfg, video_cache):
    cfg.require_ready_marker = True
    source = video_cache(0, 5)
    for role in ("mom", "child"):
        shutil.copy2(source / f"{role}.mp4", cfg.inbox_dir / f"ID100392_{role}.mp4")
    assert Pipeline(cfg).run().waiting == ["ID100392"]
    (cfg.inbox_dir / cfg.ready_marker_name).write_text("ready")
    assert Pipeline(cfg).run().newly_completed == ["ID100392"]
    assert (cfg.inbox_dir / cfg.ready_marker_name).exists()


def test_nested_marker_removed_after_promotion(cfg, video_cache):
    cfg.require_ready_marker = True
    folder = cfg.inbox_dir / "batch" / "ID100392"
    folder.mkdir(parents=True)
    source = video_cache(0, 5)
    for role in ("mom", "child"):
        shutil.copy2(source / f"{role}.mp4", folder / f"session_{role}.mp4")
    (folder / cfg.ready_marker_name).write_text("ready")
    assert Pipeline(cfg).run().newly_completed == ["ID100392"]
    assert not folder.exists()


def test_shared_folder_reprocess_preserves_other_outputs(cfg, video_cache):
    folder = cfg.inbox_dir / "batch"
    folder.mkdir()
    source = video_cache(0, 5)
    for pid in ("ID100392", "ID100534"):
        for role in ("mom", "child"):
            shutil.copy2(source / f"{role}.mp4", folder / f"{pid}_{role}.mp4")
    assert Pipeline(cfg).run().newly_completed == ["ID100392", "ID100534"]
    other = cfg.synced_dir / "batch" / "ID100534_mom_synced.mp4"
    original = (other.stat().st_size, other.stat().st_mtime_ns)
    assert Pipeline(cfg, only=["ID100392"], reprocess=["ID100392"]).run().newly_completed == ["ID100392"]
    assert (other.stat().st_size, other.stat().st_mtime_ns) == original
    assert sorted(p.name for p in (cfg.synced_dir / "batch").glob("_superseded_*/*.mp4")) == [
        "ID100392_child_synced.mp4", "ID100392_mom_synced.mp4"]


def test_reprocess_with_new_inbox_pair_does_not_reuse_old_outputs(cfg, video_cache):
    pid = "ID100392"
    source = video_cache(0, 5)
    for role in ("mom", "child"):
        shutil.copy2(source / f"{role}.mp4", cfg.inbox_dir / f"{pid}_{role}.mp4")
    assert Pipeline(cfg).run().newly_completed == [pid]
    original = cfg.synced_dir / f"{pid}_mom_synced.mp4"
    old_mtime = original.stat().st_mtime_ns
    for role in ("mom", "child"):
        shutil.copy2(source / f"{role}.mp4", cfg.inbox_dir / f"{pid}_{role}.mp4")
    result = Pipeline(cfg, only=[pid], reprocess=[pid]).run()
    assert result.manual_review == [pid]
    assert original.stat().st_mtime_ns == old_mtime
    assert not list(cfg.synced_dir.glob("_superseded_*/*.mp4"))


def test_interrupted_shared_folder_promotion_resumes(cfg, video_cache, monkeypatch):
    folder = cfg.inbox_dir / "batch"
    folder.mkdir()
    source = video_cache(0, 5)
    for role in ("mom", "child"):
        shutil.copy2(source / f"{role}.mp4", folder / f"ID100392_{role}.mp4")
    original_rename = os.rename
    count = 0

    def fail_second_move(src, dst):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("interrupted move")
        return original_rename(src, dst)

    monkeypatch.setattr(pl.os, "rename", fail_second_move)
    assert Pipeline(cfg).run().failed == ["ID100392"]
    monkeypatch.setattr(pl.os, "rename", original_rename)
    assert Pipeline(cfg).run().newly_completed == ["ID100392"]
