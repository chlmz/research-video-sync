"""Check the installed wheel outside the source checkout, without media downloads."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from rg2019 import cli, config
from rg2019.discovery import find_sources


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for flag, required in [(None, False), ("--require-all", True), ("--no-require-all", False)]:
            target = root / str(flag)
            command = ["--setup", str(target)]
            if flag:
                command.append(flag)
            assert cli.main(command) == 0
            path = target / "config.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            assert list(data["pattern"]) == ["mom", "teen", "3rd"], data
            assert all(isinstance(aliases, list) and aliases for aliases in data["pattern"].values())
            assert "mom_pattern" not in data and "child_pattern" not in data
            assert data["require_all"] is required
            cfg = config.load(path)
            for role in ["teen", "3rd"]:
                (cfg.inbox_dir / f"ID1234_{role}.mp4").touch()
            assert find_sources(cfg, cfg.inbox_dir).problem == ("MISSING" if required else None)
            assert config.from_dict({
                "followup_root": target, "mom_pattern": "_mum", "child_pattern": "_kid",
            }).camera_patterns == {"mom": ["_mum"], "child": ["_kid"]}
        legacy = root / "legacy.json"
        legacy.write_text(json.dumps({
            "followup_root": "old root", "mom_pattern": "_mum", "child_pattern": "_kid",
            "require_all": True,
        }), encoding="utf-8")
        target = root / "converted"
        assert cli.main([
            "--setup", str(target),
            "--config", str(legacy), "--no-require-all",
        ]) == 0
        converted = json.loads((target / "config.json").read_text(encoding="utf-8"))
        assert converted["pattern"] == {"mom": ["_mum"], "child": ["_kid"]}
        assert converted["require_all"] is False
        assert json.loads(legacy.read_text(encoding="utf-8"))["require_all"] is True
    print("Installed package: alias-list setup, require-all flags and legacy configs passed.")


if __name__ == "__main__":
    main()
