from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path

import pytest

from rg2019 import cli, config


DEFAULTS = config.Config(followup_root=Path("."))
SETTINGS = [
    (prefix + field.name, getattr(instance, field.name))
    for cls, instance, prefix in [
        (config.Config, DEFAULTS, ""),
        (config.SyncParams, DEFAULTS.sync, "sync."),
        (config.EncodeParams, DEFAULTS.encode, "encode."),
    ]
    for field in fields(cls)
]


@pytest.mark.parametrize("key,default", SETTINGS)
def test_every_config_field_has_a_typed_cli_override(tmp_path, key, default):
    flag = "--" + key.replace(".", "-").replace("_", "-")
    if isinstance(default, bool):
        value = not default
        args = [flag if value else "--no-" + flag[2:]]
    elif key == "pattern":
        value = {"dad": ["_dad"], "room": ["_room"]}
        args = [flag, json.dumps(value)]
    elif key == "video_extensions":
        value = [".mp4", ".m4v"]
        args = [flag, json.dumps(value)]
    elif key in {"sync", "encode"}:
        value = {"sample_rate": 16000} if key == "sync" else {"crf": 25}
        args = [flag, json.dumps(value)]
    elif key == "video_description":
        value = "pilot"
        args = [flag, value]
    elif isinstance(default, Path):
        value = tmp_path
        args = [flag, str(value)]
    else:
        value = default + 1 if isinstance(default, (int, float)) else default
        args = [flag, str(value)]
    overrides = cli.config_overrides(cli.parse_args(args))
    data = asdict(DEFAULTS)
    data["followup_root"] = tmp_path
    effective = config.from_dict(cli._apply_overrides(data, overrides))
    actual = asdict(effective)
    for part in key.split("."):
        actual = actual[part]
    if key in {"sync", "encode"}:
        assert all(actual[name] == setting for name, setting in value.items())
    else:
        assert actual == value


def test_nested_flags_override_json_without_losing_other_fields():
    args = cli.parse_args([
        "--sync-sample-rate", "16000", "--sync", '{"sample_rate":8000,"window_seconds":30}',
        "--encode", '{"preset":"slow"}', "--encode-crf", "25",
    ])
    assert cli.config_overrides(args) == {
        "sync": {"sample_rate": 16000, "window_seconds": 30},
        "encode": {"preset": "slow", "crf": 25},
    }


def test_readme_maps_every_config_field_to_its_flag():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    mapping = readme.split("### Config field to CLI flag mapping", 1)[1].split(
        "Exit code", 1)[0]
    for key, default in SETTINGS:
        flag = "--" + key.replace(".", "-").replace("_", "-")
        assert f"| `{key}` |" in mapping
        assert flag in mapping
        if isinstance(default, bool):
            assert "--no-" + flag[2:] in mapping


def test_nulls_and_worker_alias():
    args = cli.parse_args(["--pattern", "null", "--video-description", "null", "--workers", "3"])
    assert cli.config_overrides(args) == {
        "pattern": None, "video_description": None, "max_parallel_pairs": 3,
    }


def test_setup_persists_overrides_and_uses_overridden_root(tmp_path):
    target = tmp_path / "actual"
    assert cli.main([
        "--setup", str(tmp_path / "unused"), "--followup-root", str(target),
        "--inbox", "incoming", "--sync-sample-rate", "16000", "--encode-crf", "25",
        "--no-require-approval", "--video-extensions", '[".mp4",".m4v"]',
    ]) == 0
    data = json.loads((target / "config.json").read_text(encoding="utf-8"))
    assert data["followup_root"] == str(target.resolve())
    assert data["inbox"] == "incoming"
    assert data["sync"]["sample_rate"] == 16000
    assert data["encode"]["crf"] == 25
    assert data["require_approval"] is False
    assert data["video_extensions"] == [".mp4", ".m4v"]
    assert (target / "incoming").is_dir()
    assert not (tmp_path / "unused").exists()


def test_runtime_overrides_are_applied_before_tool_checks_and_do_not_edit_config(tmp_path, monkeypatch):
    root = tmp_path / "data"
    (root / "incoming").mkdir(parents=True)
    path = tmp_path / "config.json"
    original = json.dumps({"followup_root": str(tmp_path), "sync": {"window_seconds": 40}})
    path.write_text(original, encoding="utf-8")
    seen = []
    monkeypatch.setattr(cli.media, "check_tools", lambda cfg: seen.append(cfg) or {})
    assert cli.main([
        "--config", str(path), "--followup-root", str(root), "--inbox", "incoming",
        "--sync-sample-rate", "16000", "--encode-crf", "25", "--no-require-approval", "--dry-run",
    ]) == 0
    assert seen[0].sync.sample_rate == 16000 and seen[0].sync.window_seconds == 40
    assert seen[0].encode.crf == 25 and seen[0].require_approval is False
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("args", [
    ["--pattern", "{bad"], ["--sync-sample-rate", "text"], ["--max-attempts", "1.5"],
    ["--video-extensions", '"mp4"'], ["--video-extensions", "[1]"],
    ["--sync", "null"], ["--encode", "[]"],
])
def test_invalid_cli_values_fail_at_parsing(args):
    with pytest.raises(SystemExit) as exc:
        cli.parse_args(args)
    assert exc.value.code == 2


@pytest.mark.parametrize("args", [
    ["--pattern", '{"only":["_one"]}'],
    ["--sync", '{"unknown":42}'],
])
def test_invalid_nested_json_reports_config_error(tmp_path, args):
    assert cli.main(["--setup", str(tmp_path / "new")] + args) == 3
    assert not (tmp_path / "new").exists()


def test_yolo_retains_precedence_over_explicit_config_flags(tmp_path, monkeypatch):
    (tmp_path / "00_INBOX").mkdir()
    (tmp_path / "config.json").write_text(json.dumps({"followup_root": str(tmp_path)}),
                                        encoding="utf-8")
    seen = []
    monkeypatch.setattr(cli.media, "check_tools", lambda cfg: seen.append(cfg) or {})
    assert cli.main([
        str(tmp_path), "--dry-run", "--stability-minutes", "120", "--yolo",
    ]) == 0
    assert seen[0].stability_minutes == 0
