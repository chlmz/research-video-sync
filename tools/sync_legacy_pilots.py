#!/usr/bin/env python3
"""One-off legacy/pilot synchronisation utility for the RG2019 camera archive.

Purpose
-------
Scan the preserved historical pilot archive recursively, identify participant IDs from
folder names and mother/child roles from human-readable video filenames, and create
normalised curated outputs in a separate folder.

Two processing paths:

A) Raw pair (no historical sync found): use the sync estimator to align mom+child,
   re-encode both, and create a side-by-side.

B) Historical sync pair found (files in a sync/sincro subfolder with clear roles):
   re-encode the already-synced files with offset=0 and create a new side-by-side.
   The historical files are NEVER altered.

This tool is intentionally separate from ``pipeline_rg2019.py``. It NEVER moves, renames,
deletes or writes inside ``00_SOURCE_LEGACY``.

Outputs per processed participant:
    <ID>_mom_synced.mp4
    <ID>_child_synced.mp4
    <ID>_side_by_side.mp4

The synchronisation estimator and FFmpeg wrappers are reused from the production v2 code.
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from rg2019 import config as cfgmod, media, syncest
from rg2019.config import Config
from rg2019.media import MediaError, MediaInfo

log = logging.getLogger("legacy_pilots")

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}

# Maximum allowed duration difference between an already-synced mom and child.
# Historical files that were properly synchronised should have identical (or nearly
# identical) durations. A larger gap suggests mismatched files or a corrupt pair.
SYNCED_PAIR_DURATION_TOLERANCE_SECONDS: float = 2.0


class DurationMismatch(MediaError):
    """Mom and child durations differ beyond the tolerance for an already-synced pair."""

DERIVED_DIR_TERMS = {
    "sync",
    "videos sync",
    "video sync",
    "video sincro",
    "videos sincro",
    "video sincronizado",
    "videos sincronizados",
    "mp4",
    "mp42",
    "any video converter",
    "format convert",
    "adobe premiere pro auto save",
    "facereader",
    "ai facereader",
    "ai coding ic",
    "video cod",
    "videoscod",
    "material pronto",
    "logs",
    "modelagem",
}
SYNC_DIR_HINTS = ("sync", "sincro", "sincron")

MOM_EXACT = {
    "mom", "momview", "mother", "motherview", "mothe", "moth", "mothr",
    "mum", "mumview", "mummy", "parent", "parentview", "mama", "mae",
}
CHILD_EXACT = {
    "child", "childview", "children", "chil", "chid", "chld", "cild", "cildview",
    "kid", "son", "daughter", "baby",
}
MOM_FUZZY = ("mother", "parent")
CHILD_FUZZY = ("child", "children", "daughter")
SIDE_BY_SIDE_HINTS = ("side by side", "sidebyside", "brinde", "combined", "combo")


@dataclass(frozen=True)
class ParticipantId:
    display: str
    key: str


@dataclass
class Case:
    pid: ParticipantId
    folder: Path
    mom: list[Path] = field(default_factory=list)
    child: list[Path] = field(default_factory=list)
    ambiguous: list[Path] = field(default_factory=list)
    unclassified: list[Path] = field(default_factory=list)


@dataclass
class ExistingSyncedPair:
    """Files found inside a sync-named subfolder for one participant."""
    pid: ParticipantId
    mom: list[Path] = field(default_factory=list)
    child: list[Path] = field(default_factory=list)
    ambiguous: list[Path] = field(default_factory=list)
    unclassified: list[Path] = field(default_factory=list)
    derivative: list[Path] = field(default_factory=list)  # brinde/combined/side-by-side files

    @property
    def is_clear(self) -> bool:
        """Exactly one mom, one child, no ambiguous files.

        Extra unclassified or derivative (brinde/combined) files do NOT prevent a clear
        pair from being importable — they are reported in QC detail but otherwise ignored.
        """
        return len(self.mom) == 1 and len(self.child) == 1 and not self.ambiguous


@dataclass
class Result:
    participant: str
    status: str
    detail: str = ""
    mom_source: str = ""
    child_source: str = ""
    offset_seconds: str = ""
    confidence: str = ""


def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("_", " ").replace("-", " ")
    return " ".join(value.split())


def _tokens(stem: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _plain(stem))


def _fuzzy(token: str, targets: tuple[str, ...]) -> bool:
    if len(token) < 4:
        return False
    return max(SequenceMatcher(None, token, target).ratio() for target in targets) >= 0.80


def detect_role(path: Path) -> str | None:
    """Return mom, child, ambiguous or None from a filename only."""
    tokens = _tokens(path.stem)
    compact = "".join(tokens)

    mom = any(t in MOM_EXACT or _fuzzy(t, MOM_FUZZY) for t in tokens)
    child = any(t in CHILD_EXACT or _fuzzy(t, CHILD_FUZZY) for t in tokens)

    mom = mom or any(marker in compact for marker in ("momview", "motherview", "mothercam", "parentview"))
    child = child or any(marker in compact for marker in ("childview", "childcam", "cildview"))

    if mom and child:
        return "ambiguous"
    if mom:
        return "mom"
    if child:
        return "child"
    return None


def participant_id_from_component(component: str) -> ParticipantId | None:
    """Recognise the participant-ID families used in the historical pilot archive."""
    compact = re.sub(r"[^a-z0-9]", "", _plain(component))
    m = re.fullmatch(r"(id|ids|idpiloto|idromi)(\d+)", compact, flags=re.IGNORECASE)
    if not m:
        return None
    family = m.group(1).lower()
    digits = m.group(2)
    number = int(digits)
    labels = {"id": "ID", "ids": "IDS", "idpiloto": "IDPiloto", "idromi": "IDRomi"}
    return ParticipantId(f"{labels[family]}{digits}", f"{family}:{number}")


def nearest_participant_id(path: Path, root: Path) -> tuple[ParticipantId, Path] | None:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return None
    parts = rel.parts[:-1] if path.is_file() else rel.parts
    current = root
    matches: list[tuple[ParticipantId, Path]] = []
    for part in parts:
        current = current / part
        pid = participant_id_from_component(part)
        if pid is not None:
            matches.append((pid, current))
    return matches[-1] if matches else None


def _is_sync_component(name: str) -> bool:
    n = _plain(name)
    return any(h in n for h in SYNC_DIR_HINTS)


def _is_derived_component(name: str) -> bool:
    n = _plain(name)
    if n in DERIVED_DIR_TERMS:
        return True
    if _is_sync_component(name):
        return True
    if "facereader" in n:
        return True
    if "adobe premiere" in n and "auto" in n:
        return True
    return False


def _looks_side_by_side(path: Path) -> bool:
    n = _plain(path.stem)
    compact = n.replace(" ", "")
    return any(h in n or h.replace(" ", "") in compact for h in SIDE_BY_SIDE_HINTS)


def _under_derived_area(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    return any(_is_derived_component(part) for part in rel.parts[:-1])


def find_existing_synced_pairs(source_root: Path) -> dict[str, ExistingSyncedPair]:
    """All video files in sync-named subfolders, grouped by participant ID.

    Returns every participant that has at least one video inside a sync/sincro folder,
    regardless of whether the role can be determined.  Use ``pair.is_clear`` to check
    whether the pair is unambiguously importable.
    """
    pairs: dict[str, ExistingSyncedPair] = {}
    for p in source_root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        rel = p.relative_to(source_root)
        if not any(_is_sync_component(part) for part in rel.parts[:-1]):
            continue
        hit = nearest_participant_id(p, source_root)
        if hit is None:
            continue
        pid, _ = hit
        pair = pairs.setdefault(pid.key, ExistingSyncedPair(pid=pid))
        if _looks_side_by_side(p):
            pair.derivative.append(p)
            continue
        role = detect_role(p)
        if role == "mom":
            pair.mom.append(p)
        elif role == "child":
            pair.child.append(p)
        elif role == "ambiguous":
            pair.ambiguous.append(p)
        else:
            pair.unclassified.append(p)
    return pairs


def find_existing_synced_ids(source_root: Path) -> set[str]:
    """IDs with an existing historical synchronised mother+child pair (clear roles only)."""
    return {key for key, pair in find_existing_synced_pairs(source_root).items() if pair.is_clear}


def discover_cases(source_root: Path) -> dict[str, Case]:
    """Discover raw-source candidates without entering derivative/synchronised folders."""
    cases: dict[str, Case] = {}
    for p in source_root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if _under_derived_area(p, source_root) or _looks_side_by_side(p):
            continue
        hit = nearest_participant_id(p, source_root)
        if hit is None:
            continue
        pid, participant_folder = hit
        case = cases.setdefault(pid.key, Case(pid=pid, folder=participant_folder))
        role = detect_role(p)
        if role == "mom":
            case.mom.append(p)
        elif role == "child":
            case.child.append(p)
        elif role == "ambiguous":
            case.ambiguous.append(p)
        else:
            case.unclassified.append(p)
    return cases


def output_complete(output_root: Path, pid: str) -> bool:
    folder = output_root / pid
    expected = (
        folder / f"{pid}_mom_synced.mp4",
        folder / f"{pid}_child_synced.mp4",
        folder / f"{pid}_side_by_side.mp4",
    )
    return all(p.is_file() and p.stat().st_size > 0 for p in expected)


def output_needs_side_by_side(output_root: Path, pid: str) -> bool:
    """True when mom+child curated outputs exist but the side-by-side is missing."""
    folder = output_root / pid
    mom = folder / f"{pid}_mom_synced.mp4"
    child = folder / f"{pid}_child_synced.mp4"
    sbs = folder / f"{pid}_side_by_side.mp4"
    return (mom.is_file() and mom.stat().st_size > 0
            and child.is_file() and child.stat().st_size > 0
            and not sbs.exists())


def output_conflict(output_root: Path, pid: str) -> bool:
    folder = output_root / pid
    if not folder.exists():
        return False
    expected = {
        f"{pid}_mom_synced.mp4",
        f"{pid}_child_synced.mp4",
        f"{pid}_side_by_side.mp4",
    }
    present = {p.name for p in folder.iterdir() if p.is_file() and not p.name.endswith(".partial")}
    return bool(present) and not expected <= present


def load_config(path: Path | None, ffmpeg: str | None, ffprobe: str | None) -> Config:
    cfg = cfgmod.load(path) if path is not None else Config(followup_root=Path("."))
    cfg.create_side_by_side = True
    if ffmpeg:
        cfg.ffmpeg = ffmpeg
    if ffprobe:
        cfg.ffprobe = ffprobe
    return cfg


def probe_pair(cfg: Config, mom: Path, child: Path) -> dict[str, tuple[Path, MediaInfo]]:
    found: dict[str, tuple[Path, MediaInfo]] = {}
    for role, path in (("mom", mom), ("child", child)):
        info = media.probe(cfg, path)
        if not info.has_video or not info.duration or info.duration <= 0:
            raise MediaError(f"{path.name}: missing readable video stream/duration")
        if not info.has_audio:
            raise MediaError(f"{path.name}: no audio stream; automatic synchronisation is impossible")
        found[role] = (path, info)
    return found


def probe_video_pair(cfg: Config, mom: Path, child: Path) -> dict[str, tuple[Path, MediaInfo]]:
    """Probe an already-synchronised pair for import.

    Like ``probe_pair`` but does not require audio for sync estimation; audio is still
    validated because it is needed for side-by-side creation.  Raises ``DurationMismatch``
    when mom and child durations differ by more than ``SYNCED_PAIR_DURATION_TOLERANCE_SECONDS``.
    """
    found: dict[str, tuple[Path, MediaInfo]] = {}
    for role, path in (("mom", mom), ("child", child)):
        info = media.probe(cfg, path)
        if not info.has_video or not info.duration or info.duration <= 0:
            raise MediaError(f"{path.name}: missing readable video stream/duration")
        if not info.has_audio:
            raise MediaError(f"{path.name}: no audio stream; required for side-by-side creation")
        found[role] = (path, info)
    mom_dur = found["mom"][1].duration or 0.0
    child_dur = found["child"][1].duration or 0.0
    diff = abs(mom_dur - child_dur)
    if diff > SYNCED_PAIR_DURATION_TOLERANCE_SECONDS:
        raise DurationMismatch(
            f"mom {mom_dur:.3f}s vs child {child_dur:.3f}s — "
            f"difference {diff:.3f}s exceeds {SYNCED_PAIR_DURATION_TOLERANCE_SECONDS}s tolerance"
        )
    return found


def estimate(cfg: Config, pid: str, src: dict[str, tuple[Path, MediaInfo]]) -> syncest.SyncEstimate:
    prm = cfg.sync
    with tempfile.TemporaryDirectory(prefix=f"legacy_{pid}_", ignore_cleanup_errors=True) as tmp:
        arrays = {}
        for role in ("mom", "child"):
            path, _ = src[role]
            log.info("%s: extracting %d Hz mono audio from %s", pid, prm.sample_rate, path.name)
            arrays[role] = media.extract_audio(cfg, path, Path(tmp) / f"{role}.pcm", prm.sample_rate)
        est = syncest.estimate_offset(
            arrays["mom"], arrays["child"], prm,
            src["mom"][1].audio_start, src["child"][1].audio_start,
        )
        del arrays
        return est


def _commit(cfg: Config, part: Path, final: Path, expected: float | None) -> None:
    info = media.probe(cfg, part)
    if not (info.has_video and info.has_audio and info.duration and info.duration > 0):
        part.unlink(missing_ok=True)
        raise MediaError(f"{final.name}: encoded file failed ffprobe validation")
    if expected is not None and abs(info.duration - expected) > cfg.encode.duration_tolerance_seconds:
        part.unlink(missing_ok=True)
        raise MediaError(f"{final.name}: duration {info.duration:.2f}s differs from expected {expected:.2f}s")
    os.replace(part, final)


def encode_outputs(
    cfg: Config,
    pid: str,
    output_root: Path,
    src: dict[str, tuple[Path, MediaInfo]],
    offset: float,
) -> None:
    out = output_root / pid
    out.mkdir(parents=True, exist_ok=True)

    mom_final = out / f"{pid}_mom_synced.mp4"
    child_final = out / f"{pid}_child_synced.mp4"
    side_final = out / f"{pid}_side_by_side.mp4"
    finals = (mom_final, child_final, side_final)

    if any(p.exists() for p in finals):
        raise FileExistsError(f"{out}: one or more final outputs already exist; refusing to overwrite")

    for stale in out.glob("*.partial"):
        stale.unlink(missing_ok=True)

    mom_trim, child_trim = syncest.trim_plan(offset, cfg.encode.min_trim_seconds)
    try:
        for role, final, trim in (
            ("mom", mom_final, mom_trim),
            ("child", child_final, child_trim),
        ):
            source, info = src[role]
            part = final.with_name(final.name + ".partial")
            log.info("%s: writing %s (trim %.3f s)", pid, final.name, trim)
            media.encode(cfg, source, part, trim, info)
            _commit(cfg, part, final, (info.duration or 0) - trim)

        side_part = side_final.with_name(side_final.name + ".partial")
        log.info("%s: writing %s", pid, side_final.name)
        media.side_by_side(cfg, mom_final, child_final, side_part)
        _commit(cfg, side_part, side_final, None)
    except Exception:
        for p in out.glob("*.partial"):
            p.unlink(missing_ok=True)
        raise


def create_side_by_side_only(cfg: Config, pid: str, output_root: Path) -> None:
    """Create the side-by-side from existing curated mom+child outputs (no re-encode)."""
    out = output_root / pid
    mom_final = out / f"{pid}_mom_synced.mp4"
    child_final = out / f"{pid}_child_synced.mp4"
    side_final = out / f"{pid}_side_by_side.mp4"
    if side_final.exists():
        raise FileExistsError(f"{side_final}: side-by-side already exists")
    side_part = side_final.with_name(side_final.name + ".partial")
    try:
        log.info("%s: writing %s from existing curated pair", pid, side_final.name)
        media.side_by_side(cfg, mom_final, child_final, side_part)
        _commit(cfg, side_part, side_final, None)
    except Exception:
        for p in out.glob("*.partial"):
            p.unlink(missing_ok=True)
        raise


def write_report(output_root: Path, results: list[Result]) -> Path:
    qc = output_root / "_QC"
    qc.mkdir(parents=True, exist_ok=True)
    path = qc / f"legacy_sync_report_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "participant", "status", "detail", "mom_source", "child_source",
                "offset_seconds", "confidence",
            ],
        )
        writer.writeheader()
        for r in results:
            writer.writerow(r.__dict__)
    return path


def print_results(results: list[Result]) -> None:
    if not results:
        print("No participant cases found.")
        return
    print()
    print(f"{'PARTICIPANT':<18} {'STATUS':<24} DETAIL")
    print("-" * 100)
    for r in results:
        detail = r.detail if len(r.detail) <= 62 else r.detail[:59] + "..."
        print(f"{r.participant:<18} {r.status:<24} {detail}")


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="One-off recursive synchronisation of preserved RG2019 legacy/pilot videos"
    )
    ap.add_argument("--source-root", type=Path, required=True,
                    help="immutable historical root, e.g. PILOTS/00_SOURCE_LEGACY")
    ap.add_argument("--output-root", type=Path, required=True,
                    help="curated destination, e.g. PILOTS/01_CURATED_INPUTS/SYNCED")
    ap.add_argument("--config", type=Path,
                    help="optional production config.json; only ffmpeg/sync/encode settings are reused")
    ap.add_argument("--ffmpeg", help="override ffmpeg executable/path")
    ap.add_argument("--ffprobe", help="override ffprobe executable/path")
    ap.add_argument("--participant", action="append", metavar="ID",
                    help="restrict to participant ID (repeatable)")
    ap.add_argument("--dry-run", action="store_true",
                    help="discovery only: write/change nothing")
    ap.add_argument("--log-level", default="INFO", choices=["INFO", "DEBUG"])
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()

    if not source_root.is_dir():
        print(f"ERROR: source root does not exist: {source_root}", file=sys.stderr)
        return 3
    try:
        output_root.relative_to(source_root)
    except ValueError:
        pass
    else:
        print("ERROR: output-root must not be inside 00_SOURCE_LEGACY", file=sys.stderr)
        return 3

    cfg = load_config(args.config, args.ffmpeg, args.ffprobe)
    if not args.dry_run:
        try:
            versions = media.check_tools(cfg)
        except MediaError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3
        for exe, version in versions.items():
            log.info("%s: %s", exe, version)

    synced_pairs = find_existing_synced_pairs(source_root)
    cases = discover_cases(source_root)

    # Merge all sources so participants with only sync-folder or partial output files are covered.
    all_pids: dict[str, ParticipantId] = {k: v.pid for k, v in cases.items()}
    for key, pair in synced_pairs.items():
        if key not in all_pids:
            all_pids[key] = pair.pid
    # Also include participants found only in the output root (e.g. prior partial runs).
    if output_root.is_dir():
        for d in output_root.iterdir():
            if not d.is_dir() or d.name.startswith("_"):
                continue
            pid_obj = participant_id_from_component(d.name)
            if pid_obj is not None and pid_obj.key not in all_pids:
                all_pids[pid_obj.key] = pid_obj

    wanted: set[str] | None = None
    if args.participant:
        wanted = set()
        for raw in args.participant:
            pid = participant_id_from_component(raw)
            if pid is None:
                print(f"ERROR: unsupported participant ID: {raw}", file=sys.stderr)
                return 3
            wanted.add(pid.key)

    results: list[Result] = []

    for key in sorted(all_pids, key=lambda k: all_pids[k].display.lower()):
        if wanted is not None and key not in wanted:
            continue
        pid = all_pids[key].display
        case = cases.get(key)
        pair = synced_pairs.get(key)

        if output_complete(output_root, pid):
            results.append(Result(pid, "ALREADY_COMPLETE", "all three curated outputs exist"))
            continue
        if output_needs_side_by_side(output_root, pid):
            if args.dry_run:
                results.append(Result(pid, "WOULD_ADD_SIDE_BY_SIDE",
                                      "curated mom+child exist; only side-by-side is missing"))
            else:
                try:
                    create_side_by_side_only(cfg, pid, output_root)
                    results.append(Result(pid, "ADD_SIDE_BY_SIDE",
                                          "side-by-side created from existing curated pair"))
                except (MediaError, OSError, ValueError, FileExistsError) as exc:
                    results.append(Result(pid, "FAILED", str(exc)))
            continue
        if output_conflict(output_root, pid):
            results.append(Result(pid, "REVIEW_OUTPUT_CONFLICT",
                                  "partial/unrecognised curated outputs exist; nothing overwritten"))
            continue

        if pair is not None:
            if pair.is_clear:
                mom, child = pair.mom[0], pair.child[0]
                extras = [p.name for p in pair.unclassified + pair.derivative]
                base_detail = "historical synced mom+child found; will re-encode and create side-by-side"
                if extras:
                    base_detail += "; extras (ignored): " + ", ".join(extras)
                if args.dry_run:
                    results.append(Result(pid, "WOULD_IMPORT_EXISTING_SYNC", base_detail,
                                          str(mom), str(child)))
                else:
                    try:
                        src = probe_video_pair(cfg, mom, child)
                        encode_outputs(cfg, pid, output_root, src, 0.0)
                        results.append(Result(
                            pid, "IMPORT_EXISTING_SYNC",
                            "imported historical synced pair; side-by-side created",
                            str(mom), str(child),
                        ))
                    except DurationMismatch as exc:
                        results.append(Result(pid, "REVIEW_DURATION_MISMATCH",
                                              str(exc), str(mom), str(child)))
                    except (MediaError, OSError, ValueError, FileExistsError) as exc:
                        results.append(Result(pid, "FAILED", str(exc), str(mom), str(child)))
            else:
                details: list[str] = []
                if len(pair.mom) != 1:
                    details.append(f"mom={len(pair.mom)}" + (": " + ", ".join(p.name for p in pair.mom) if pair.mom else ""))
                if len(pair.child) != 1:
                    details.append(f"child={len(pair.child)}" + (": " + ", ".join(p.name for p in pair.child) if pair.child else ""))
                if pair.ambiguous:
                    details.append("ambiguous=" + ", ".join(p.name for p in pair.ambiguous))
                if pair.unclassified:
                    details.append("unclassified=" + ", ".join(p.name for p in pair.unclassified))
                results.append(Result(pid, "REVIEW_SYNCED_AMBIGUOUS", "; ".join(details)))
            continue

        if case is None:
            continue

        if case.ambiguous:
            results.append(Result(
                pid, "REVIEW_AMBIGUOUS_ROLE",
                "filename matches both mom and child: " + ", ".join(p.name for p in case.ambiguous),
            ))
            continue
        if len(case.mom) != 1 or len(case.child) != 1:
            details = [f"mom={len(case.mom)}", f"child={len(case.child)}"]
            if case.unclassified:
                details.append("unclassified=" + ", ".join(p.name for p in case.unclassified))
            results.append(Result(pid, "REVIEW_FILES", "; ".join(details)))
            continue

        mom, child = case.mom[0], case.child[0]
        if args.dry_run:
            results.append(Result(
                pid, "WOULD_PROCESS",
                "one mom + one child found; will create mom/child synced + side-by-side",
                str(mom), str(child),
            ))
            continue

        try:
            src = probe_pair(cfg, mom, child)
            est = estimate(cfg, pid, src)
            if not est.ok or est.offset_seconds is None:
                results.append(Result(
                    pid, "REVIEW_LOW_CONFIDENCE", est.reason,
                    str(mom), str(child),
                    "" if est.offset_seconds is None else f"{est.offset_seconds:.6f}",
                    f"{est.confidence:.4f}",
                ))
                continue
            log.info("%s: offset %+.4f s (confidence %.2f; %s)",
                     pid, est.offset_seconds, est.confidence, est.reason)
            encode_outputs(cfg, pid, output_root, src, est.offset_seconds)
            results.append(Result(
                pid, "SUCCESS", est.reason, str(mom), str(child),
                f"{est.offset_seconds:.6f}", f"{est.confidence:.4f}",
            ))
        except (MediaError, OSError, ValueError, FileExistsError) as exc:
            results.append(Result(pid, "FAILED", str(exc), str(mom), str(child)))

    print_results(results)

    if args.dry_run:
        return 0 if not any(r.status.startswith("REVIEW") or r.status == "FAILED" for r in results) else 2

    report = write_report(output_root, results)
    print(f"\nQC report: {report}")
    problems = [r for r in results if r.status.startswith("REVIEW") or r.status == "FAILED"]
    return 2 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
