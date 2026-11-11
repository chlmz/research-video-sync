from __future__ import annotations

import json

import pytest

from rg2019 import cli, config
from rg2019.discovery import discover_jobs, find_sources


@pytest.mark.parametrize("mode,label,stem,expected", [
    ("auto", "_mom", "visit_MOM_extra", True),
    ("auto", "*mom", "ID1234_MOM", True),
    ("auto", "*mom", "ID1234_MOM_extra", False),
    ("prefix", "mom_", "MOM_ID1234", True),
    ("prefix", "mom_", "ID1234_mom_extra", False),
    ("prefix", "mom_", "ID1234_mom_", False),
    ("suffix", "_mom", "ID1234_MOM", True),
    ("suffix", "_mom", "mom_ID1234", False),
    ("suffix", "_mom", "ID1234_mom_extra", False),
    ("prefix", "mom[1]_", "mom[1]_ID1234", True),
    ("prefix", "mom*", "mom_ID1234", False),
    ("suffix", "_mom?", "ID1234_mom1", False),
    ("regex", r"(^|_)mom(_|$)", "visit_MOM_ID1234", True),
    ("regex", r"(^|_)mom(_|$)", "visit_mommy_ID1234", False),
    ("regex", r"^mom_", "ID1234_mom_extra", False),
    ("regex", r"_mom$", "ID1234_mom_extra", False),
    ("regex", r"mom_\D+$", "mom_ABC", True),
    ("regex", r"mom_\D+$", "mom_123", False),
    ("regex", r"(?-i:MOM)_", "MOM_ID1234", True),
    ("regex", r"(?-i:MOM)_", "mom_ID1234", False),
])
def test_camera_pattern_modes(tmp_path, mode, label, stem, expected):
    cfg = config.from_dict({
        "followup_root": str(tmp_path),
        "pattern_mode": mode,
        "pattern": {"mom": [label, "mother_"], "child": ["child_"]},
    })
    assert cfg.matching_roles(stem) == (["mom"] if expected else [])
    assert cfg.matching_roles("mother_") == ["mom"]


@pytest.mark.parametrize("mode", [None, "", "glob", "REGEX", 1, True, [], {}])
def test_invalid_pattern_mode_rejected(tmp_path, mode):
    with pytest.raises(config.ConfigError, match="pattern_mode"):
        config.from_dict({"followup_root": str(tmp_path), "pattern_mode": mode})


@pytest.mark.parametrize("legacy", [False, True])
def test_invalid_regex_rejected_before_setup_writes(tmp_path, legacy):
    patterns = ({"mom_pattern": "(", "child_pattern": "child"} if legacy else
                {"pattern": {"mom": ["mom", "("], "child": "child"}})
    with pytest.raises(config.ConfigError, match="mom.*valid regex"):
        config.from_dict({"followup_root": str(tmp_path), "pattern_mode": "regex", **patterns})
    target = tmp_path / "new"
    args = ["--setup", str(target), "--pattern-mode", "regex",
            "--pattern", '{"mom":["mom","("],"child":["child"]}']
    assert cli.main(args) == 3
    assert not target.exists()


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("mode,mom,child,names", [
    ("prefix", "mom_", "child_", ["MOM_ID1234.mp4", "child_ID1234.mov"]),
    ("suffix", "_mom", "_child", ["ID1234_MOM.mp4", "ID1234_child.mov"]),
    ("regex", r"(^|_)mom(_|$)", r"(^|_)child(_|$)",
     ["visit_MOM_ID1234.mp4", "visit_child_ID1234.mov"]),
])
def test_modes_used_by_folder_and_shared_discovery(tmp_path, legacy, mode, mom, child, names):
    patterns = ({"mom_pattern": mom, "child_pattern": child} if legacy else
                {"pattern": {"mom": [mom], "child": [child]}})
    cfg = config.from_dict({
        "followup_root": str(tmp_path), "pattern_mode": mode, **patterns,
    })
    cfg.inbox_dir.mkdir()
    for name in names:
        (cfg.inbox_dir / name).touch()
    found = find_sources(cfg, cfg.inbox_dir)
    assert found.problem is None
    assert found.roles["mom"][0].name == names[0]
    assert found.roles["child"][0].name == names[1]
    assert discover_jobs(cfg, cfg.inbox_dir)["ID1234"].files == found.files
    # A second file for the same camera must never be silently selected.
    (cfg.inbox_dir / names[0]).with_suffix(".avi").touch()
    assert find_sources(cfg, cfg.inbox_dir).problem == "AMBIGUOUS"
    assert discover_jobs(cfg, cfg.inbox_dir)["ID1234"].problem == "AMBIGUOUS"


def test_regex_matching_multiple_roles_is_ambiguous(tmp_path):
    cfg = config.from_dict({
        "followup_root": str(tmp_path), "pattern_mode": "regex",
        "pattern": {"mom": ["mom"], "child": ["child"]},
    })
    (tmp_path / "ID1234_mom_child.mp4").touch()
    assert find_sources(cfg, tmp_path).problem == "AMBIGUOUS"


@pytest.mark.parametrize("mode", ["prefix", "suffix", "regex"])
def test_cli_mode_override_and_setup_persistence(tmp_path, mode):
    target = tmp_path / mode
    assert cli.main([
        "--setup", str(target), "--pattern-mode", mode,
        "--pattern", '{"mom":["mom"],"child":["child"]}',
    ]) == 0
    cfg = config.load(target / "config.json")
    assert cfg.pattern_mode == mode
    assert json.loads((target / "config.json").read_text())["pattern_mode"] == mode
    overrides = cli.config_overrides(cli.parse_args(["--pattern-mode", "auto"]))
    data = cli._apply_overrides(json.loads((target / "config.json").read_text()), overrides)
    assert config.from_dict(data).pattern_mode == "auto"
    assert config.load(target / "config.json").pattern_mode == mode


def test_regex_preflight_preserves_filename_case_for_unsupported_extensions(tmp_path):
    cfg = config.from_dict({
        "followup_root": str(tmp_path), "pattern_mode": "regex",
        "pattern": {"mom": [r"(?-i:MOM)_"], "child": ["child_"]},
    })
    folder = cfg.inbox_dir / "ID1234"
    folder.mkdir(parents=True)
    path = folder / "MOM_ID1234.xyz"
    path.touch()
    report, _, _ = cli.preflight_inventory(cfg)
    assert "No configured video suffix: 1" in report
    assert path.name in report
