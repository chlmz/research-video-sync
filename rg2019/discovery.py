"""Participant-id validation and mother/child source discovery.

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

    @property
    def problem(self) -> str | None:
        """None if exactly one mom and one child; otherwise 'MISSING' or 'AMBIGUOUS'."""
        if self.both or len(self.mom) > 1 or len(self.child) > 1:
            return "AMBIGUOUS"
        if not self.mom or not self.child:
            return "MISSING"
        return None

    def describe(self) -> str:
        def names(xs):
            return ", ".join(p.name for p in xs) or "none"
        return (f"mom candidates: [{names(self.mom)}]; child candidates: [{names(self.child)}]"
                + (f"; matching both patterns: [{names(self.both)}]" if self.both else ""))


def find_sources(cfg: Config, folder: Path) -> Discovery:
    """Look (non-recursively) for the mother and child videos in `folder`."""
    d = Discovery()
    mom_p, child_p = cfg.mom_pattern.lower(), cfg.child_pattern.lower()
    for p in sorted(folder.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file() or is_junk_file(p.name) or is_transit_file(p.name):
            continue
        if p.suffix.lower() not in cfg.video_extensions:
            continue
        stem = p.stem.lower()
        is_mom, is_child = mom_p in stem, child_p in stem
        if is_mom and is_child:
            d.both.append(p)
        elif is_mom:
            d.mom.append(p)
        elif is_child:
            d.child.append(p)
    return d
