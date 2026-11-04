"""Lightweight tests for the independent TeenCam entry points."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from sync_inbox import discover
from sync_inbox import main as sync_inbox_main
from sync_three_cameras_v2 import candidates
from sync_three_cameras_v2 import main as sync_three_cameras_main


def touch(folder, *names):
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"synthetic fixture")


def test_inbox_accepts_two_and_three_camera_sets(tmp_path):
    inbox = tmp_path / "00_INBOX"
    touch(inbox, "#2181 snack task mum view point.AVI",
          "#2181 snack task teen view point.AVI",
          "#2341 Snack task parent view point.AVI",
          "#2341 Snack task teen view point.AVI",
          "#2341 Snack task third camera.AVI")
    groups = discover(inbox)
    assert len(groups["#2181"]["mom"]) == 1
    assert len(groups["#2181"]["child"]) == 1
    assert "third" not in groups["#2181"]
    assert len(groups["#2341"]["third"]) == 1


def test_duplicates_not_silently_accepted(tmp_path):
    inbox = tmp_path / "00_INBOX"
    touch(inbox, "#2181 snack mum view point.AVI",
          "#2181 snack parent view point.AVI",
          "#2181 snack teen view point.AVI")
    cfg = SimpleNamespace(raw_dir=tmp_path/"01_RAW", inbox_dir=inbox,
                          video_extensions=[".avi"], mom_pattern="parent view point",
                          child_pattern="teen view point")
    with pytest.raises(ValueError, match="found 0"):
        candidates(cfg, "#2181")


def test_candidate_selection_works_for_two_and_three_cameras(tmp_path):
    inbox = tmp_path / "00_INBOX"
    touch(inbox, "#2181 snack mum view point.AVI",
          "#2181 snack teen view point.AVI",
          "#2341 snack parent view point.AVI",
          "#2341 snack teen view point.AVI",
          "#2341 snack third camera.AVI")
    cfg = SimpleNamespace(raw_dir=tmp_path/"01_RAW", inbox_dir=inbox,
                          video_extensions=[".avi"], mom_pattern="parent view point",
                          child_pattern="teen view point")
    _, _, two = candidates(cfg, "#2181")
    _, _, three = candidates(cfg, "#2341")
    assert set(two) == {"mom", "child"}
    assert set(three) == {"mom", "child", "third"}


def test_candidate_selection_accepts_default_patterns_with_teen_labels(tmp_path):
    inbox = tmp_path / "00_INBOX"
    touch(inbox, "#2181 snack mum view point.AVI",
          "#2181 snack teen view point.AVI",
          "#2341 snack parent view point.AVI",
          "#2341 snack teen view point.AVI",
          "#2341 snack third camera.AVI")
    cfg = SimpleNamespace(raw_dir=tmp_path / "01_RAW", inbox_dir=inbox,
                          video_extensions=[".avi"], mom_pattern="_mom",
                          child_pattern="_child")

    _, _, two = candidates(cfg, "#2181")
    _, _, three = candidates(cfg, "#2341")

    assert set(two) == {"mom", "child"}
    assert set(three) == {"mom", "child", "third"}


def test_inbox_does_not_accept_camera_files_split_across_folders(tmp_path, monkeypatch, capsys):
    inbox = tmp_path / "00_INBOX"
    touch(inbox / "first", "#2181 parent view point.AVI")
    touch(inbox / "second", "#2181 teen view point.AVI")
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    cfg = SimpleNamespace(
        followup_root=tmp_path, inbox_dir=inbox,
        mom_pattern="parent view point", child_pattern="teen view point",
        video_extensions=[".avi"],
    )
    monkeypatch.setattr("sync_inbox.config.load", lambda _: cfg)
    monkeypatch.setattr(sys, "argv", [
        "sync_inbox.py", "--root", str(tmp_path), "--config", str(config_path),
    ])
    invoked = []
    monkeypatch.setattr("sync_inbox.subprocess.run", lambda *args, **kwargs: invoked.append(args))

    result = sync_inbox_main()

    assert result == 1
    assert not invoked
    assert "0 valid 2- or 3-camera sets" in capsys.readouterr().out


def test_inbox_launches_complete_three_camera_set(tmp_path, monkeypatch, capsys):
    inbox = tmp_path / "00_INBOX"
    touch(inbox, "#2341 parent view point.AVI",
          "#2341 teen view point.AVI",
          "#2341 third camera.AVI")
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    cfg = SimpleNamespace(
        followup_root=tmp_path, inbox_dir=inbox,
        mom_pattern="parent view point", child_pattern="teen view point",
        video_extensions=[".avi"],
    )
    monkeypatch.setattr("sync_inbox.config.load", lambda _: cfg)
    monkeypatch.setattr(sys, "argv", [
        "sync_inbox.py", "--root", str(tmp_path), "--config", str(config_path),
    ])
    invoked = []

    def run(command, check):
        invoked.append((command, check))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("sync_inbox.subprocess.run", run)

    result = sync_inbox_main()

    assert result == 0
    assert len(invoked) == 1
    command, check = invoked[0]
    assert "--id" in command
    assert command[command.index("--id") + 1] == "#2341"
    assert check is False
    assert "1 valid 2- or 3-camera sets" in capsys.readouterr().out


def test_discovery_uses_configured_patterns_and_extensions(tmp_path):
    inbox = tmp_path / "00_INBOX"
    touch(inbox, "#2181 parent-camera.AVI",
          "#2181 teen-camera.AVI",
          "#2181 third camera.m4v")

    groups = discover(
        inbox,
        mom_pattern="parent-camera",
        child_pattern="teen-camera",
        video_extensions=["m4v", ".avi"],
    )

    assert set(groups["#2181"]) == {"mom", "child", "third"}


def test_three_camera_preview_uses_one_shared_timeline(tmp_path, monkeypatch, capsys):
    paths = {role: tmp_path / f"{role}.mp4" for role in ("mom", "child", "third")}
    durations = {"mom": 100.0, "child": 90.0, "third": 80.0}
    cfg = SimpleNamespace(
        followup_root=tmp_path,
        participant_id_regex=r"#\d+",
        sync=SimpleNamespace(min_overlap_seconds=10.0),
        create_side_by_side=False,
        video_description=None,
    )
    info = {
        role: SimpleNamespace(has_video=True, has_audio=True, duration=durations[role], audio_start=0.0)
        for role in paths
    }
    monkeypatch.setattr("sync_three_cameras_v2.config.load", lambda _: cfg)
    monkeypatch.setattr("sync_three_cameras_v2.media.check_tools", lambda _: None)
    monkeypatch.setattr("sync_three_cameras_v2.candidates", lambda *_: (tmp_path, tmp_path, paths))
    monkeypatch.setattr("sync_three_cameras_v2.media.probe", lambda _, path: info[path.stem])
    monkeypatch.setattr(
        "sync_three_cameras_v2.audio_offset",
        lambda _, __, ___, ____, _____, ______, label: {"child": 5.0, "third": -3.0}[label],
    )
    monkeypatch.setattr(sys, "argv", [
        "sync_three_cameras_v2.py", "--config", str(tmp_path / "config.json"), "--id", "#2181",
    ])

    sync_three_cameras_main()

    output = capsys.readouterr().out
    assert "Common duration: 72.000 s" in output
    assert "mom: trim 5.000 s" in output
    assert "child: trim 0.000 s" in output
    assert "third: trim 8.000 s" in output


def test_failed_camera_encode_does_not_leave_partial_output_set(tmp_path, monkeypatch):
    paths = {role: tmp_path / f"{role}.mp4" for role in ("mom", "child", "third")}
    cfg = SimpleNamespace(
        followup_root=tmp_path,
        participant_id_regex=r"#\d+",
        sync=SimpleNamespace(min_overlap_seconds=10.0),
        encode=SimpleNamespace(
            video_codec="libx264",
            preset="fast",
            crf=20,
            audio_bitrate="192k",
            duration_tolerance_seconds=1.5,
        ),
        ffmpeg="ffmpeg",
        create_side_by_side=False,
        video_description=None,
    )
    info = SimpleNamespace(has_video=True, has_audio=True, duration=100.0, audio_start=0.0)
    monkeypatch.setattr("sync_three_cameras_v2.config.load", lambda _: cfg)
    monkeypatch.setattr("sync_three_cameras_v2.media.check_tools", lambda _: None)
    monkeypatch.setattr("sync_three_cameras_v2.candidates", lambda *_: (tmp_path, tmp_path, paths))
    monkeypatch.setattr("sync_three_cameras_v2.media.probe", lambda *_: info)
    monkeypatch.setattr("sync_three_cameras_v2.audio_offset", lambda *args: 0.0)

    def run_media(command, _):
        source = Path(command[command.index("-i") + 1])
        target = Path(command[-1])
        if source.stem == "third":
            raise RuntimeError("synthetic encoder failure")
        target.write_bytes(b"encoded")

    monkeypatch.setattr("sync_three_cameras_v2.media._run", run_media)
    monkeypatch.setattr(sys, "argv", [
        "sync_three_cameras_v2.py", "--config", str(tmp_path / "config.json"),
        "--id", "#2181", "--apply",
    ])

    with pytest.raises(RuntimeError, match="synthetic encoder failure"):
        sync_three_cameras_main()

    output_dir = tmp_path / "02_SYNCED_3CAM" / "#2181"
    assert not list(output_dir.iterdir())
