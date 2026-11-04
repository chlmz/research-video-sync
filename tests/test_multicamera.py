from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from helpers import make_video, recording, wall_signal
from rg2019 import cli, config, media, syncest
from rg2019.discovery import discover_jobs, find_sources
from rg2019.pipeline import Outcome, Pipeline, PreparedPair
from rg2019.state import StateStore, new_state
from rg2019.statuses import S


def camera_config(root, pattern):
    return config.from_dict({
        "followup_root": str(root),
        "pattern": pattern,
        "require_approval": False,
        "stability_recheck_seconds": 0,
        "sync": {"sample_rate": 8000, "window_seconds": 2, "max_lag_seconds": 6,
                 "fine_search_seconds": 0.5, "min_overlap_seconds": 3},
        "encode": {"preset": "ultrafast", "crf": 30},
    })


@pytest.mark.parametrize("pattern", [
    {}, {"only": "_only"}, {"mom": [] , "teen": "_teen"},
    {"mom": [None], "teen": "_teen"}, {"../escape": "_x", "teen": "_teen"},
    {"Dad": "_dad", "dad": "_teen"}, {"side_by_side": "_x", "teen": "_teen"},
])
def test_invalid_patterns_rejected(tmp_path, pattern):
    with pytest.raises(config.ConfigError, match="pattern"):
        camera_config(tmp_path, pattern)


def test_ordered_aliases_globs_and_optional_cameras(tmp_path):
    cfg = camera_config(tmp_path, {"dad": ["*dad", "_papa"], "teen": "teen", "room": "_wide"})
    folder = cfg.inbox_dir / "ID1234"
    folder.mkdir(parents=True)
    for name in ("ID1234_PAPA.mp4", "ID1234_teen.mp4", "ID1234_WIDE.mp4"):
        (folder / name).touch()
    found = find_sources(cfg, folder)
    assert found.problem is None
    assert list(found.roles) == ["dad", "teen", "room"]
    assert found.roles["dad"][0].name == "ID1234_PAPA.mp4"
    assert cfg.matching_roles("ID1234_DAD") == ["dad"]
    assert cfg.matching_roles("ID1234_dad_extra") == []
    assert discover_jobs(cfg, cfg.inbox_dir)["ID1234"].files == found.files
    (folder / "ID1234_WIDE.mp4").unlink()
    assert find_sources(cfg, folder).problem is None
    (folder / "ID1234_teen.mp4").unlink()
    assert find_sources(cfg, folder).problem == "MISSING"


def test_ambiguous_optional_camera_and_cross_folder_are_rejected(tmp_path):
    cfg = camera_config(tmp_path, {"dad": "_dad", "teen": "_teen", "room": "_wide"})
    folder = cfg.inbox_dir / "ID1234"
    folder.mkdir(parents=True)
    for name in ("ID1234_dad.mp4", "ID1234_teen.mp4", "ID1234_wide.mp4",
                 "ID1234_wide_copy.mp4"):
        (folder / name).touch()
    assert find_sources(cfg, folder).problem == "AMBIGUOUS"
    (folder / "ID1234_wide_copy.mp4").unlink()
    (folder / "ID1234_dad_teen.mp4").touch()
    assert find_sources(cfg, folder).problem == "AMBIGUOUS"
    (folder / "ID1234_dad_teen.mp4").unlink()
    other = cfg.inbox_dir / "other"
    other.mkdir()
    (folder / "ID1234_wide.mp4").rename(other / "ID1234_wide.mp4")
    assert discover_jobs(cfg, cfg.inbox_dir)["ID1234"].problem == "AMBIGUOUS"


@pytest.mark.parametrize("count", [3, 4])
def test_full_pipeline_aligns_named_cameras_and_resumes(tmp_path, count, monkeypatch):
    names = ["dad", "teen", "room", "door"][:count]
    cfg = camera_config(tmp_path, {name: f"_{name}" for name in names})
    folder = cfg.inbox_dir / "ID1234"
    folder.mkdir(parents=True)
    rate = 8000
    wall = wall_signal(32, rate, seed=64)
    starts = [0, 2, 4, 1][:count]
    for name, start in zip(names, starts):
        make_video(folder / f"ID1234_{name}.mp4", recording(wall, rate, start, 24), rate, 24)
    original_hashes = {path.name: media.sha256_file(path) for path in folder.iterdir()}

    preview = Pipeline(cfg, dry_run=True).run()
    assert preview.would_process == ["ID1234"]
    assert not cfg.state_dir.exists()
    assert not cfg.raw_dir.exists()
    report = cli.preflight_report(cfg)
    assert f"Will sync: {count} source video(s)" in report

    if count == 3:
        with monkeypatch.context() as patch:
            def interrupted(*args):
                raise media.MediaError("grid encode interrupted")
            patch.setattr(media, "camera_grid", interrupted)
            interrupted_result = Pipeline(cfg).run()
            assert interrupted_result.failed == ["ID1234"]
        interrupted_state = StateStore(cfg).load("ID1234", "now")
        assert set(interrupted_state["outputs"]["files"]) == set(names)
        with monkeypatch.context() as patch:
            def should_not_repeat(*args, **kwargs):
                pytest.fail("completed camera outputs and offsets must be reused")
            patch.setattr(media, "encode", should_not_repeat)
            patch.setattr(syncest, "estimate_offset", should_not_repeat)
            result = Pipeline(cfg).run()
    else:
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(asdict(cfg), default=str), encoding="utf-8")
        assert cli.main(["--config", str(config_path)]) == 0
        result = Pipeline(cfg).run()
    assert (result.newly_completed if count == 3 else result.skipped_completed) == ["ID1234"], result.render()
    st = StateStore(cfg).load("ID1234", "now")
    assert st["camera_order"] == names
    assert set(st["outputs"]["files"]) == {*names, "side_by_side"}
    for name, start in zip(names, starts):
        assert st["sync"]["offsets"][name] == pytest.approx(start, abs=0.06)
    assert st["sync"]["duration"] == pytest.approx(20, abs=0.06)
    for name in names:
        rec = st["outputs"]["files"][name]
        assert rec["name"] == f"ID1234_{name}_synced.mp4"
        assert rec["duration"] == pytest.approx(20, abs=0.15)
    combined = cfg.synced_dir / "ID1234" / st["outputs"]["files"]["side_by_side"]["name"]
    info = media.probe(cfg, combined)
    assert (info.width, info.height) == (1280, 720)
    assert info.duration == pytest.approx(20, abs=0.15)
    samples = []
    try:
        for name in names:
            output = cfg.synced_dir / "ID1234" / st["outputs"]["files"][name]["name"]
            samples.append(media.extract_audio(cfg, output, tmp_path / f"{name}.pcm", rate))
        for other in samples[1:]:
            estimate = syncest.estimate_offset(samples[0], other, cfg.sync)
            assert estimate.ok and abs(estimate.offset_seconds) < 0.03, estimate.reason
    finally:
        for sample in samples:
            sample._mmap.close()
    assert {path.name: media.sha256_file(path) for path in (cfg.raw_dir / "ID1234").iterdir()} == original_hashes
    assert not (cfg.logs_dir / "work" / "ID1234").exists()
    with cfg.status_csv.open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert set(json.loads(row["camera_sources"])) == set(names)
    assert json.loads(row["camera_offsets"]) == st["sync"]["offsets"]
    assert Pipeline(cfg).run().skipped_completed == ["ID1234"]
    # Changing camera order must never silently reuse the old layout or offsets.
    cfg.pattern = {name: f"_{name}" for name in reversed(names)}
    assert Pipeline(cfg).run().outcomes[0].status == S.RAW_CONFLICT
    rerun = Pipeline(cfg, reprocess=["ID1234"]).run()
    assert rerun.newly_completed == ["ID1234"], rerun.render()
    assert StateStore(cfg).load("ID1234", "now")["camera_order"] == list(reversed(names))


def test_later_camera_tries_previously_aligned_cameras_in_order(tmp_path, monkeypatch):
    cfg = camera_config(tmp_path, {"dad": "_dad", "teen": "_teen", "room": "_room", "door": "_door"})
    st = new_state("ID1234", "now")
    src = {}
    for role in cfg.camera_patterns:
        info = media.MediaInfo(1, 100, "mp4", 0, video_codec="h264", audio_codec="aac")
        src[role] = (tmp_path / f"{role}.mp4", info)
        st["sources"][role] = {"name": f"{role}.mp4", "media": info.to_dict()}
    job = PreparedPair("ID1234", st, src, tmp_path / "out")
    pipe = Pipeline(cfg)
    monkeypatch.setattr(pipe, "_save", lambda _: None)
    monkeypatch.setattr("rg2019.pipeline.checkpoints.audio",
                        lambda cfg, state, role, source, save: SimpleNamespace(
                            role=role, _mmap=SimpleNamespace(close=lambda: None)))
    calls = []

    def estimate(anchor, other, *args):
        calls.append((anchor.role, other.role))
        if (anchor.role, other.role) == ("dad", "room"):
            return syncest.SyncEstimate(False, None, 0, "no shared sound")
        offset = {("dad", "teen"): 2, ("teen", "room"): 3, ("dad", "door"): -1}[anchor.role, other.role]
        return syncest.SyncEstimate(True, offset, 1, "matched")

    monkeypatch.setattr(syncest, "estimate_offset", estimate)
    encoded = []
    monkeypatch.setattr(pipe, "_encode_all", lambda *args: encoded.append(args) or Outcome("ID1234", S.SUCCESS))
    result = pipe._finish_cameras(job)
    assert result.status == S.SUCCESS
    assert calls == [("dad", "teen"), ("dad", "room"), ("teen", "room"), ("dad", "door")]
    assert st["sync"]["offsets"] == {"dad": 0, "teen": 2, "room": 5, "door": -1}
    assert st["sync"]["trims"] == {"dad": 5, "teen": 3, "room": 0, "door": 6}
    assert st["sync"]["duration"] == 94
    assert len(encoded) == 1


def test_unalignable_present_camera_never_encodes(tmp_path, monkeypatch):
    cfg = camera_config(tmp_path, {"dad": "_dad", "teen": "_teen", "room": "_room"})
    st = new_state("ID1234", "now")
    src = {role: (tmp_path / f"{role}.mp4", media.MediaInfo(
        1, 100, "mp4", 0, video_codec="h264", audio_codec="aac")) for role in cfg.camera_patterns}
    pipe = Pipeline(cfg)
    monkeypatch.setattr(pipe, "_save", lambda _: None)
    monkeypatch.setattr("rg2019.pipeline.checkpoints.audio",
                        lambda cfg, state, role, source, save: SimpleNamespace(
                            role=role, _mmap=SimpleNamespace(close=lambda: None)))
    monkeypatch.setattr(syncest, "estimate_offset", lambda anchor, other, *args:
                        syncest.SyncEstimate(other.role == "teen", 2, 1, "fixture"))
    monkeypatch.setattr(pipe, "_encode_all", lambda *args: pytest.fail("must not encode an unaligned set"))
    result = pipe._finish_cameras(PreparedPair("ID1234", st, src, tmp_path / "out"))
    assert result.status == S.LOW_CONFIDENCE
    assert "room" in result.message


@pytest.mark.parametrize("count", [3, 4, 5])
def test_grid_positions_colors_and_black_blank_cell(tmp_path, count):
    cfg = camera_config(tmp_path, {"a": "_a", "b": "_b"})
    colors = ["red", "green", "blue", "yellow", "magenta"][:count]
    videos = []
    for index, color in enumerate(colors):
        path = tmp_path / f"{index}.mp4"
        media._run([
            cfg.ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i",
            f"color=c={color}:s=160x90:r=10:d=0.5",
            "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono",
            "-t", "0.5", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path),
        ], "color fixture")
        videos.append(path)
    output = tmp_path / "grid.mp4"
    media.camera_grid(cfg, videos, output)
    height = ((count + 1) // 2) * 360
    info = media.probe(cfg, output)
    assert (info.width, info.height) == (1280, height)
    result = subprocess.run([
        cfg.ffmpeg, "-v", "error", "-i", str(output), "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ], capture_output=True, check=True)
    pixels = np.frombuffer(result.stdout, dtype=np.uint8).reshape(height, 1280, 3)
    expected = [(255, 0, 0), (0, 128, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)]
    for index in range(count):
        actual = pixels[(index // 2) * 360 + 180, (index % 2) * 640 + 320]
        assert np.allclose(actual, expected[index], atol=12), (index, actual)
    if count % 2:
        assert np.max(pixels[height - 180, 960]) < 12


def test_setup_defaults_use_unified_pattern_mapping(tmp_path):
    target = tmp_path / "new"
    path = cli.setup_project(target, target / "config.json")
    data = json.loads(path.read_text())
    assert list(data["pattern"])[:2] == ["mom", "teen"]
    assert "mom_pattern" not in data and "child_pattern" not in data
    assert config.load(path).camera_patterns["mom"] == ["_mom", "_mum"]


def test_shared_inbox_keeps_each_participants_optional_cameras(tmp_path, monkeypatch):
    cfg = camera_config(tmp_path, {"dad": "_dad", "teen": "_teen", "room": "_room"})
    cfg.inbox_dir.mkdir()
    for pid in ("ID1234", "ID5678"):
        for role in cfg.camera_patterns:
            (cfg.inbox_dir / f"{pid}_{role}.mp4").write_bytes(b"synthetic fixture")
    monkeypatch.setattr(media, "probe", lambda *args: media.MediaInfo(
        17, 100, "mp4", 0, video_codec="h264", audio_codec="aac"))
    prepared = []

    def finish(self, job):
        prepared.append(job)
        return Outcome(job.pid, S.SUCCESS, kind="new")

    monkeypatch.setattr(Pipeline, "_finish_raw", finish)
    result = Pipeline(cfg).run()
    assert result.newly_completed == ["ID1234", "ID5678"], result.render()
    assert len(prepared) == 2
    for job in prepared:
        assert list(job.sources) == ["dad", "teen", "room"]
        assert all(path.name.startswith(job.pid) for path, _ in job.sources.values())
        assert all(path.parent == cfg.raw_dir for path, _ in job.sources.values())


def test_changed_camera_order_cannot_resume_partial_promotion(tmp_path):
    cfg = camera_config(tmp_path, {"dad": "_dad", "teen": "_teen", "room": "_room"})
    folder = cfg.inbox_dir / "ID1234"
    folder.mkdir(parents=True)
    for role in cfg.camera_patterns:
        (folder / f"ID1234_{role}.mp4").write_bytes(b"fixture")
    st = new_state("ID1234", "now")
    st["stage"] = "PROMOTING"
    st["camera_order"] = list(cfg.camera_patterns)
    st["sources"] = {role: {"name": f"ID1234_{role}.mp4"} for role in cfg.camera_patterns}
    StateStore(cfg).save(st)
    cfg.pattern = {"teen": "_teen", "dad": "_dad", "room": "_room"}
    result = Pipeline(cfg).run()
    assert result.outcomes[0].status == S.RAW_CONFLICT
    assert "during promotion" in result.outcomes[0].message
    assert len(list(folder.iterdir())) == 3
    assert not cfg.raw_dir.exists()


def test_changed_alias_assignment_cannot_reuse_completed_cameras(tmp_path):
    cfg = camera_config(tmp_path, {"dad": "_teen", "teen": "_dad"})
    folder = cfg.raw_dir / "ID1234"
    folder.mkdir(parents=True)
    for role in cfg.camera_patterns:
        (folder / f"ID1234_{role}.mp4").write_bytes(b"fixture")
    st = new_state("ID1234", "now")
    st["stage"] = "RAW"
    st["camera_order"] = list(cfg.camera_patterns)
    st["sources"] = {role: {"name": f"ID1234_{role}.mp4"} for role in cfg.camera_patterns}
    pipe = Pipeline(cfg)
    result = pipe._from_raw("ID1234", st, folder, cfg.synced_dir / "ID1234")
    assert result.status == S.RAW_CONFLICT
    assert "--reprocess" in result.message


def test_legacy_state_requires_reprocess_on_every_attempt(tmp_path):
    cfg = camera_config(tmp_path, {"mom": "_mom", "child": "_child"})
    folder = cfg.raw_dir / "ID1234"
    folder.mkdir(parents=True)
    st = new_state("ID1234", "now")
    st["stage"] = "SYNCED"
    st["sync_completed_at"] = "then"
    for role in cfg.camera_patterns:
        (folder / f"ID1234_{role}.mp4").write_bytes(b"fixture")
        st["sources"][role] = {"name": f"ID1234_{role}.mp4"}
    pipe = Pipeline(cfg)
    for _ in range(2):
        result = pipe._from_raw("ID1234", st, folder, cfg.synced_dir / "ID1234")
        assert result.status == S.RAW_CONFLICT
        st = pipe.store.load("ID1234", "now")
        assert "camera_order" not in st


def test_changed_manual_offset_does_not_reuse_partial_outputs(tmp_path):
    cfg = camera_config(tmp_path, {"dad": "_dad", "teen": "_teen"})
    st = new_state("ID1234", "now")
    st["sync"] = {"offsets": {"dad": 0, "teen": 2}}
    st["outputs"]["files"] = {"dad": {"name": "ID1234_dad_synced.mp4"}}
    pipe = Pipeline(cfg, only=["ID1234"], manual_offset=3)
    src = {role: (tmp_path / f"{role}.mp4", None) for role in cfg.camera_patterns}
    result = pipe._finish_cameras(PreparedPair("ID1234", st, src, tmp_path / "out"))
    assert result.status == S.OUTPUT_CONFLICT
    assert st["sync"]["offsets"]["teen"] == 2
