"""Participant-id validation and ordered camera source discovery.

Discovery is deliberately strict: it never picks "the first match".  Zero or several
plausible candidates for either role are reported to the caller, which stops the
participant and flags it for manual review.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config

# Names that are never participants / never sources (Synology, Windows, macOS artefacts).
IGNORED_DIR_PREFIXES = (".", "@", "#", "$")
IGNORED_FILE_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
# Files that indicate a transfer is still in progress (Synology Drive / browsers / editors).
TRANSIT_SUFFIXES = (".tmp", ".partial", ".part", ".crdownload", ".download", ".filepart")
TRANSIT_PREFIXES = (".~", "~$", ".syno")


def is_ignored_dir(name: str) -> bool:
    return name.startswith(IGNORED_DIR_PREFIXES)


def is_transit_file(name: str) -> bool:
    low = name.lower()
    return low.endswith(TRANSIT_SUFFIXES) or low.startswith(TRANSIT_PREFIXES)


def is_junk_file(name: str) -> bool:
    return name.lower() in IGNORED_FILE_NAMES


def valid_participant_id(cfg: Config, name: str) -> bool:
    return re.fullmatch(cfg.participant_id_regex, name) is not None


@dataclass
class Discovery:
    mom: list[Path] = field(default_factory=list)
    child: list[Path] = field(default_factory=list)
    both: list[Path] = field(default_factory=list)   # match BOTH patterns -> ambiguous
    cameras: dict[str, list[Path]] = field(default_factory=dict)
    require_all: bool = False

    @property
    def roles(self) -> dict[str, list[Path]]:
        return self.cameras or {"mom": self.mom, "child": self.child}

    @property
    def files(self) -> list[Path]:
        return [path for paths in self.roles.values() for path in paths]

    def add(self, cfg: Config, path: Path) -> None:
        roles = cfg.matching_roles(path.stem)
        if len(roles) > 1:
            self.both.append(path)
        elif roles:
            self.roles[roles[0]].append(path)

    @property
    def problem(self) -> str | None:
        """Require all configured cameras, or any two; all matches remain unambiguous."""
        if (self.both or any(len(paths) > 1 for paths in self.roles.values())
                or len({path.parent for path in self.files}) > 1):
            return "AMBIGUOUS"
        if (sum(bool(paths) for paths in self.roles.values()) < 2
                or (self.require_all and any(not paths for paths in self.roles.values()))):
            return "MISSING"
        return None

    def describe(self) -> str:
        def names(xs):
            return ", ".join(p.name for p in xs) or "none"
        return ("; ".join(f"{role} candidates: [{names(paths)}]" for role, paths in self.roles.items())
                + (f"; matching both patterns: [{names(self.both)}]" if self.both else ""))


def find_sources(cfg: Config, folder: Path) -> Discovery:
    """Look non-recursively for configured cameras in `folder`."""
    d = _discovery(cfg)
    for p in sorted(folder.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file() or is_junk_file(p.name) or is_transit_file(p.name):
            continue
        if p.suffix.lower() not in cfg.video_extensions:
            continue
        d.add(cfg, p)
    return d


def _discovery(cfg: Config) -> Discovery:
    if cfg.pattern is None:
        return Discovery(require_all=cfg.require_all)
    cameras = {role: [] for role in cfg.camera_patterns}
    first, second = list(cameras.values())[:2]
    return Discovery(mom=first, child=second, cameras=cameras, require_all=cfg.require_all)


def video_id(cfg: Config, path: Path, root: Path) -> str | None:
    """Find an ID in the stem first, then in the nearest containing directory."""
    pattern = cfg.participant_id_regex.removeprefix("^").removesuffix("$")

    def matches(text: str) -> list[str]:
        return [m.group() for m in re.finditer(pattern, text)
                if (m.start() == 0 or not text[m.start() - 1].isdigit())
                and (m.end() == len(text) or not text[m.end()].isdigit())
                and valid_participant_id(cfg, m.group())]

    found = matches(path.stem)
    if found:
        return found[0] if len(set(found)) == 1 else None
    for parent in path.relative_to(root).parents:
        if parent == Path("."):
            break
        found = matches(parent.name)
        if found:
            return found[0] if len(set(found)) == 1 else None
    return None


def discover_jobs(cfg: Config, root: Path) -> dict[str, Discovery]:
    """Group videos by ID without pairing across directories or taking a first match."""
    jobs: dict[str, Discovery] = {}
    if not root.is_dir():
        return jobs
    for path in sorted(root.rglob("*")):
        if (not path.is_file() or any(is_ignored_dir(p.name) and not valid_participant_id(cfg, p.name)
                                      for p in path.relative_to(root).parents if p != Path("."))
                or is_junk_file(path.name) or is_transit_file(path.name)
                or path.suffix.lower() not in cfg.video_extensions):
            continue
        pid = video_id(cfg, path, root)
        if pid is None:
            continue
        job = jobs.setdefault(pid, _discovery(cfg))
        job.add(cfg, path)
    return jobs
