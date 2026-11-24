#!/usr/bin/env python3
"""September-2026 *NumPy* audio FFT + current nested RG2019 field layout.

Creates local, UNAPPROVED candidate videos. Never moves, edits or publishes sources.
This intentionally does not invoke the newer NCC/window consensus gate.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
import wave

import numpy as np

EXTENSIONS = {".avi", ".mp4", ".mov", ".mkv"}
ROLE = re.compile(r"(?<![a-z0-9])(mother|mom|children|child)(\d*)(?![a-z0-9])", re.I)
FIELD_TAG = re.compile(
    r"(?<![a-z0-9])((?:take|toma|session|sesión|sessão|visita?|game|juego|jogo)"
    r"[-_ ]?[a-z0-9]+|\d{4}[-_]\d{2}[-_]\d{2})(?![a-z0-9])", re.I)
GAME_TAG = re.compile(r"(?:game|juego|jogo)([0-9]+)$")
CAMERA_DIR = re.compile(r"(?:cam(?:era)?[-_ ]?[a-z0-9]+|(?:\d+[a-z]?)?(?:mother|mom|child|children)\d*|[mc])", re.I)
TRANSIT = (".tmp", ".partial", ".part", ".download", ".filepart", ".crdownload")


class SyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class Job:
    participant: str
    session: str
    game: int
    mom: Path
    child: Path
    selection: str  # explicit_game or reviewed_single_unnumbered


@dataclass(frozen=True)
class ReviewPolicy:
    """Provisional review gates, applied only after the September peak was selected."""
    min_overlap_seconds: float = 1.0
    distinct_lag_seconds: float = 0.05
    competing_peak_fraction: float = 0.8
    quiet_pcm_level: int = 32
    min_active_fraction: float = 0.01

    def __post_init__(self):
        if not (math.isfinite(self.min_overlap_seconds) and self.min_overlap_seconds > 0
                and math.isfinite(self.distinct_lag_seconds) and self.distinct_lag_seconds > 0
                and 0 < self.competing_peak_fraction <= 1 and 0 < self.min_active_fraction <= 1
                and 0 <= self.quiet_pcm_level < 32768):
            raise SyncError("invalid acoustic review policy")


def safe_session(value: str) -> str:
    if not value or "\\" in value or ":" in value or value.startswith("/"):
        raise SyncError("session root must be a relative POSIX path")
    if any(p in ("", "..") for p in value.split("/")):
        raise SyncError("session root contains traversal or empty components")
    return value


def linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def role_game(path: Path, session_dir: Path) -> tuple[str | None, int | None, str | None]:
    """Classify explicit mother1/children1 names; no guessing from camera or SNAP."""
    parts = path.relative_to(session_dir).parts
    found = [m for part in (*parts[:-1], path.stem) for m in ROLE.finditer(part)]
    roles = {"mom" if m.group(1).lower() in {"mother", "mom"} else "child" for m in found}
    numbers = {int(m.group(2)) for m in found if m.group(2)}
    if len(roles) != 1 or len(numbers) > 1 or any(n < 1 or n > 99 for n in numbers):
        return None, None, "unclassified/contradictory role or game"
    return next(iter(roles)), next(iter(numbers)) if numbers else None, None


def matching_context(mom: Path, child: Path, participant_dir: Path, game: int) -> bool:
    """Require matching recording labels and field branches outside camera storage."""
    def context(video: Path):
        relative = video.relative_to(participant_dir)
        tags = set()
        field_dirs, storage_dirs = [], []
        folders = field_dirs
        for part in (*relative.parts[:-1], relative.stem):
            for match in FIELD_TAG.finditer(part):
                tags.add(re.sub(r"[-_ ]", "", match[0].casefold()))
        for part in relative.parts[:-1]:
            if part.casefold() == "dcim":
                folders = storage_dirs
            elif not (CAMERA_DIR.fullmatch(part) or FIELD_TAG.fullmatch(part)):
                folders.append(part.casefold())
        return tags, field_dirs, storage_dirs

    tags, field, storage = context(mom)
    child_tags, child_field, child_storage = context(child)
    if tags != child_tags or field != child_field:
        return False
    for tag in tags:
        marker = GAME_TAG.fullmatch(tag)
        if marker and int(marker[1]) != game:
            return False
    # Cameras can add an extra DCIM level; diverging named subtrees are unresolved.
    shared = min(len(storage), len(child_storage))
    return storage[:shared] == child_storage[:shared]


def find_jobs(root: Path, participant: str, session: str) -> tuple[list[Job], list[str]]:
    """Scan only explicitly bounded participant/session, recursively, without writes."""
    if not re.fullmatch(r"\d{6}", participant):
        raise SyncError("participant must be a six-digit string")
    session = safe_session(session)
    participant_dir = root / participant
    session_dir = participant_dir / session
    if not participant_dir.is_dir() or not session_dir.is_dir():
        raise SyncError("participant/session directory missing")
    if linked(participant_dir) or linked(session_dir):
        raise SyncError("participant/session is a link/junction")
    checked = session_dir.resolve(strict=True)
    if not checked.is_relative_to(participant_dir.resolve(strict=True)):
        raise SyncError("session directory escapes participant tree")
    groups: dict[int | None, dict[str, list[Path]]] = {}
    issues: list[str] = []
    for walk_root, dirs, files in os.walk(session_dir, followlinks=False):
        here = Path(walk_root)
        if linked(here) or not here.resolve(strict=True).is_relative_to(checked):
            issues.append(f"linked/escaped directory excluded: {here.relative_to(session_dir)}")
            dirs[:] = []
            continue
        for d in list(dirs):
            target = here / d
            if linked(target):
                dirs.remove(d)
                issues.append(f"linked directory excluded: {(target).relative_to(session_dir)}")
        for filename in files:
            src = here / filename
            if filename.lower().endswith(TRANSIT):
                issues.append(f"transfer in progress: {src.relative_to(session_dir)}")
                continue
            if src.suffix.lower() not in EXTENSIONS:
                continue  # 360-degree auxiliary and historical JSON are never pairs
            if not src.is_file() or linked(src) or not src.resolve(strict=True).is_relative_to(checked):
                issues.append(f"linked/unsupported video excluded: {src.relative_to(session_dir)}")
                continue
            role, game, problem = role_game(src, session_dir)
            if problem:
                issues.append(f"{problem}: {src.relative_to(session_dir)}")
                continue
            groups.setdefault(game, {"mom": [], "child": []})[role].append(src)
    # At this point issues are session-wide: an excluded or unidentified file
    # may be an alternate source for any of the apparently complete games.
    if issues:
        return [], issues
    if None in groups:
        unnumbered = groups.pop(None)
        # One unique unnumbered pair is game1, only inside the explicitly selected session.
        if (not groups and len(unnumbered["mom"]) == 1 and len(unnumbered["child"]) == 1):
            groups[1] = unnumbered
            inferred = True
        else:
            issues.append("unnumbered pair is ambiguous; specify a reviewed single-pair session")
            return [], issues
    else:
        inferred = False
    jobs: list[Job] = []
    for game in sorted(groups):
        pair = groups[game]
        if len(pair["mom"]) != 1 or len(pair["child"]) != 1:
            issues.append(f"game {game} needs exactly one mother and one child; found {len(pair['mom'])}/{len(pair['child'])}")
            continue
        mom, child = pair["mom"][0], pair["child"][0]
        if not matching_context(mom, child, participant_dir, game):
            issues.append(f"game {game} has conflicting session, game or take context; review exact pair")
            continue
        jobs.append(Job(participant, session, game, mom, child,
                        "reviewed_single_unnumbered" if inferred else "explicit_game"))
    # Never silently treat unknown extra AVIs as validated session completeness.
    return jobs, issues


def september_offset(mom_wav: Path, child_wav: Path, policy: ReviewPolicy = ReviewPolicy()) -> dict:
    """September NumPy full-audio FFT (no NCC or window thresholds).

    The historical RMS-normalized global maximum is preserved. Only its index ->
    linear lag conversion is fixed for very unequal durations.
    """
    def wav(path: Path):
        with wave.open(str(path), "rb") as f:
            if (f.getnchannels(), f.getsampwidth()) != (1, 2):
                raise SyncError("expected mono signed PCM 16-bit WAV")
            rate = f.getframerate()
            a = np.frombuffer(f.readframes(f.getnframes()), dtype="<i2")
        if not len(a):
            raise SyncError("empty WAV")
        a = a.astype(np.float32)
        rms = float(np.sqrt(np.mean(a.astype(np.float64) ** 2))) or 1.0
        return a / rms, rate, rms
    a, rate, rms_a = wav(mom_wav)
    b, rate2, rms_b = wav(child_wav)
    if rate != rate2:
        raise SyncError("WAV sample rates differ")
    n = a.size + b.size - 1
    corr = np.fft.irfft(np.fft.rfft(a, n=n) * np.conj(np.fft.rfft(b, n=n)), n=n)
    k = int(np.argmax(corr))
    # Linear support for C(k)=sum_j mom[j+k]*child[j]:  -(N-1)..M-1.
    lag = k if k < len(a) else k - n
    overlap = max(0, min(len(a), len(b) + lag) - max(0, lag)) / rate
    # Inspect the existing correlation in *linear* lag coordinates. Never change
    # the selected peak or restrict its search. These are review flags only.
    gap = max(1, math.ceil(policy.distinct_lag_seconds * rate))
    alternatives = []
    for lower, upper in ((1 - len(b), min(lag - gap, len(a) - 1)),
                         (max(1 - len(b), lag + gap), len(a) - 1)):
        for lo, hi in ((lower, min(-1, upper)), (max(0, lower), upper)):
            if lo <= hi:
                segment = corr[lo % n:hi % n + 1]
                alt = lo + int(np.argmax(segment))
                alternatives.append((float(corr[alt % n]), alt / rate))
    competing_peak, competing_offset = max(alternatives) if alternatives else (None, None)
    start_a, start_b = max(0, lag), max(0, -lag)
    count = min(len(a) - start_a, len(b) - start_b)
    def active_fraction(signal, rms):
        return float(np.mean(np.abs(signal) > policy.quiet_pcm_level / rms))
    active = dict(mom=active_fraction(a[start_a:start_a+count], rms_a),
                  child=active_fraction(b[start_b:start_b+count], rms_b))
    reasons = []
    if overlap < policy.min_overlap_seconds:
        reasons.append("INSUFFICIENT_AUDIO_OVERLAP")
    if min(active.values()) < policy.min_active_fraction or corr[k] <= 0:
        reasons.append("INSUFFICIENT_ACTIVE_AUDIO")
    if competing_peak is not None and corr[k] > 0 and competing_peak >= corr[k] * policy.competing_peak_fraction:
        reasons.append("COMPETING_FFT_PEAK")
    return dict(offset_seconds=lag / rate, peak_raw=float(corr[k]),
                overlap_seconds=overlap, sample_rate=rate,
                mom_audio_seconds=len(a) / rate, child_audio_seconds=len(b) / rate,
                competing_peak_raw=competing_peak, competing_offset_seconds=competing_offset,
                active_overlap_fraction=active, review_reasons=reasons,
                method="september_2026_numpy_full_audio_fft")


def run_command(cmd: list[str], label: str) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                       encoding="utf-8", errors="replace")
    if p.returncode:
        raise SyncError(f"{label} failed (exit {p.returncode}): {(p.stderr or '')[-1100:]}")


def checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while data := f.read(8 * 1024 * 1024):
            h.update(data)
    return h.hexdigest()


def copy_source(src: Path, dst: Path) -> str:
    before = src.stat()
    if linked(src):
        raise SyncError("source became a link")
    # No modification of the source; copy once to local scratch.
    shutil.copyfile(src, dst)
    after = src.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise SyncError("source changed during read")
    digest = checksum(dst)
    # Verify local snapshot against source bytes; fail closed on mid-copy edits.
    if checksum(src) != digest:
        raise SyncError("source SHA differs from copied bytes")
    return digest


def ffprobe_media(ffprobe: str, path: Path) -> dict:
    p = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format",
                        "-of", "json", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    if p.returncode:
        raise SyncError(f"ffprobe failed: {(p.stderr or '')[-800:]}")
    data = json.loads(p.stdout)
    streams = data.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) != 1:
        raise SyncError("pair member must have exactly one video and one audio stream")
    video, audio = videos[0], audios[0]
    duration = float(data["format"]["duration"])
    rate = video.get("avg_frame_rate")
    if rate in (None, "0/0", "0/1"):
        rate = video.get("r_frame_rate")
    if rate in (None, "0/0", "0/1"):
        raise SyncError("video frame rate is unavailable")
    fps = float(Fraction(rate))
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(fps) or fps <= 0:
        raise SyncError("invalid duration or frame rate")
    return dict(video=video["codec_name"], audio=audio["codec_name"],
                duration_seconds=duration, frame_rate=fps, container=data["format"]["format_name"],
                video_start=float(video.get("start_time", 0)), audio_start=float(audio.get("start_time", 0)),
                video_seconds=float(video.get("duration", duration)), audio_seconds=float(audio.get("duration", duration)),
                sample_rate=int(audio["sample_rate"]), width=int(video["width"]), height=int(video["height"]))


def encode(ffmpeg: str, src: Path, target: Path, trim: float, duration: float) -> None:
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-n", "-i", str(src)]
    if trim > 0:
        cmd.extend(["-ss", f"{trim:.6f}"])  # September: -ss AFTER input, accurate re-encode
    cmd.extend(["-t", f"{duration:.6f}", "-map", "0:v:0", "-map", "0:a:0", "-c:v", "libx264",
                "-fps_mode", "passthrough",
                "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                "-f", "mp4", str(target)])
    run_command(cmd, "encode")


def make_side_by_side(ffmpeg: str, mother: Path, child: Path, target: Path) -> None:
    flt = ("[0:v]scale=-2:720,setpts=PTS-STARTPTS[left];"
           "[1:v]scale=-2:720,setpts=PTS-STARTPTS[right];"
           "[left][right]hstack=inputs=2:shortest=1[v];"
           "[0:a][1:a]amix=inputs=2:duration=shortest[a]")
    run_command([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
                 "-i", str(mother), "-i", str(child), "-filter_complex", flt,
                 "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast",
                 "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart", "-f", "mp4", str(target)], "side-by-side")


def verify_candidate(ffmpeg: str, ffprobe: str, path: Path, duration: float, tolerance: float) -> dict:
    media = ffprobe_media(ffprobe, path)
    if ("mp4" not in media["container"].split(",") or media["video"] != "h264" or media["audio"] != "aac"):
        raise SyncError("candidate must be H.264/AAC MP4")
    for kind in ("video", "audio"):
        if abs(media[kind + "_start"]) > tolerance or abs(media[kind + "_seconds"] - duration) > tolerance:
            raise SyncError(f"unexpected {kind} timing for {path.name}: {media}")
    run_command([ffmpeg, "-nostdin", "-v", "error", "-xerror", "-err_detect", "explode", "-i", str(path),
                 "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"], "full output decode")
    return dict(filename=path.name, sha256=checksum(path), size=path.stat().st_size, media=media,
                fully_decoded=True)


def target_folder(output_root: Path, job: Job) -> Path:
    if not re.fullmatch(r"\d{6}", job.participant) or not isinstance(job.game, int) or not 1 <= job.game <= 99:
        raise SyncError("invalid participant or game in output identity")
    safe_session(job.session)
    slug = hashlib.sha256(job.session.encode("utf-8")).hexdigest()[:12]
    return output_root / job.participant / f"session-{slug}" / f"game-{job.game:02d}"


def execute_job(job: Job, output_root: Path, *, ffmpeg="ffmpeg", ffprobe="ffprobe",
                sample_rate=16000, output_prefix: str | None = None, max_offset_seconds: float = 30.0,
                review_policy: ReviewPolicy = ReviewPolicy()) -> tuple[Path, dict]:
    """Process a candidate pair only to a new LOCAL QC directory."""
    final = target_folder(output_root, job)
    prefix = output_prefix if output_prefix is not None else f"{job.participant}_g{job.game:02d}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", prefix):
        raise SyncError("invalid output prefix")
    if not math.isfinite(max_offset_seconds) or max_offset_seconds < 0:
        raise SyncError("invalid review offset limit")
    if any(linked(source) or not source.is_file() for source in (job.mom, job.child)):
        raise SyncError("pair must identify two regular source files")
    if job.mom.samefile(job.child):
        raise SyncError("identical explicit pair")
    outside_input(output_root, [job.mom, job.child])
    if final.exists():
        raise SyncError(f"candidate output already exists; will not overwrite: {final}")
    final.parent.mkdir(parents=True, exist_ok=True)
    attempt = final.with_name(f".{final.name}.work-{uuid.uuid4().hex[:8]}")
    attempt.mkdir()
    work = attempt / "scratch"
    work.mkdir()
    copied, source_hashes, input_media = {}, {}, {}
    for role, source in (("mom", job.mom), ("child", job.child)):
        dest = work / f"{role}{source.suffix.lower()}"
        source_hashes[role] = copy_source(source, dest)
        copied[role] = dest
        input_media[role] = ffprobe_media(ffprobe, dest)
        run_command([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-n",
                     "-i", str(dest), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(sample_rate),
                     "-c:a", "pcm_s16le", "-f", "wav", str(work / f"{role}.wav")], "audio extraction")
    evidence = september_offset(work / "mom.wav", work / "child.wav", review_policy)
    offset = evidence["offset_seconds"]
    trims = {"mom": max(0., offset), "child": max(0., -offset)}
    filenames = dict(mom=f"{prefix}_mom_synced.mp4", child=f"{prefix}_child_synced.mp4",
                     side_by_side=f"{prefix}_side_by_side.mp4")
    reasons = evidence["review_reasons"]
    if abs(offset) > max_offset_seconds:
        reasons.append("OFFSET_EXCEEDS_REVIEW_LIMIT")
    duration = min(evidence["overlap_seconds"], *(min(m["video_seconds"], m["audio_seconds"]) - trims[role]
                                                  for role, m in input_media.items()))
    if duration < review_policy.min_overlap_seconds:
        reasons.append("INSUFFICIENT_AV_OVERLAP")
    if source_hashes["mom"] == source_hashes["child"]:
        reasons.append("IDENTICAL_SOURCE_CONTENT")
    for role, m in input_media.items():
        if abs(m["video_start"] - m["audio_start"]) > max(1/m["frame_rate"], 1024/m["sample_rate"]):
            reasons.append(f"{role.upper()}_AUDIO_VIDEO_ORIGINS_DIFFER")
    output_meta = {}
    if not reasons:
        for role in ("mom", "child"):
            encode(ffmpeg, copied[role], attempt / filenames[role], trims[role], duration)
        make_side_by_side(ffmpeg, attempt / filenames["mom"], attempt / filenames["child"],
                          attempt / filenames["side_by_side"])
        tolerance = max(max(1/m["frame_rate"], 1024/m["sample_rate"]) for m in input_media.values()) + 0.002
        for role, filename in filenames.items():
            output_meta[role] = verify_candidate(ffmpeg, ffprobe, attempt/filename, duration, tolerance)
    report = dict(schema="rg2019.september-adapter.v2", timestamp=datetime.now(timezone.utc).isoformat(),
                  participant=job.participant, session_root=job.session, game=job.game,
                  pairing=job.selection, inputs=dict(mom=str(job.mom), child=str(job.child)),
                  input_sha256=source_hashes, input_media=input_media, **evidence,
                  trims={} if reasons else trims, common_seconds=duration, outputs=output_meta,
                  review_policy=dict(max_offset_seconds=max_offset_seconds, **vars(review_policy)),
                  status="NEEDS_REVIEW" if reasons else "CANDIDATE_FOR_MANUAL_QC", qc_status="NotApproved",
                  warning="Unqualified September full-audio correlation maximum; NOT scientifically validated")
    (attempt / "sync_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Never promote temporary source media or audio to a candidate-output directory.
    shutil.rmtree(work)
    if final.exists():
        raise SyncError("output destination appeared concurrently; source/attempt preserved")
    attempt.rename(final)
    return final, report


def outside_input(output: Path, sources: list[Path], source_tree: Path | None = None) -> None:
    if str(output).startswith(("\\\\", "//")):
        raise SyncError("output root must be local; network/UNC publication is disabled")
    resolved_output = output.resolve()
    if str(resolved_output).startswith(("\\\\", "//")):
        raise SyncError("resolved output root must not be a network/UNC path")
    if source_tree is not None and (resolved_output.is_relative_to(source_tree.resolve(strict=True))
                                    or source_tree.resolve(strict=True).is_relative_to(resolved_output)):
        raise SyncError("output root must be outside the entire source tree")
    for p in sources:
        source = p.resolve(strict=True)
        if source == resolved_output or resolved_output.is_relative_to(source) or source.is_relative_to(resolved_output):
            raise SyncError("output root must not overlap source paths")


def plan(args) -> tuple[list[Job], list[str]]:
    issues: list[str] = []
    if (args.mom is None) != (args.child is None):
        raise SyncError("--mom and --child must be provided together")
    if args.mom is not None:
        if len(args.participant or []) != 1 or len(args.session_root or []) != 1 or args.game is None:
            raise SyncError("explicit pair needs one --participant, one --session-root and --game")
        if not re.fullmatch(r"\d{6}", args.participant[0]):
            raise SyncError("participant must be a six-digit string")
        if linked(args.mom) or linked(args.child):
            raise SyncError("linked explicit pair")
        mom, child = args.mom.resolve(strict=True), args.child.resolve(strict=True)
        if mom.samefile(child) or not mom.is_file() or not child.is_file():
            raise SyncError("invalid or identical explicit pair")
        return [Job(args.participant[0], safe_session(args.session_root[0]), args.game, mom, child,
                    "explicit_user_pair")], issues
    cfg = {}
    if args.config:
        cfg = json.loads(args.config.read_text(encoding="utf-8-sig"))
    if args.source_root:
        source_root = args.source_root
    elif cfg.get("followup_root"):
        source_root = Path(cfg["followup_root"]) / cfg.get("inbox", "00_INBOX")
    else:
        raise SyncError("supply --config (with followup_root) or --source-root pointing at 00_INBOX")
    source_root = source_root.resolve(strict=True)
    if not source_root.is_dir():
        raise SyncError("source-root is not a directory")
    sessions = cfg.get("field_sessions", {})
    if not isinstance(sessions, dict):
        raise SyncError("field_sessions must be a dict of participant -> session roots")
    if args.session_root:
        if len(args.participant or []) != 1:
            raise SyncError("--session-root override requires exactly one --participant")
        sessions = dict(sessions, **{args.participant[0]: args.session_root})
    participants = args.participant or sorted(sessions)
    if not participants:
        raise SyncError("no reviewed sessions defined; pass --participant + --session-root")
    jobs = []
    for participant in participants:
        for session in sessions.get(participant, []):
            new, warning = find_jobs(source_root, participant, session)
            jobs.extend(new)
            issues.extend(f"{participant} / {session}: {x}" for x in warning)
    if not jobs:
        issues.append("No unambiguous mother/child pair in configured sessions")
    if args.game is not None:
        jobs = [j for j in jobs if j.game == args.game]
    return jobs, issues


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, help="optional existing local config.json (field_sessions)")
    ap.add_argument("--source-root", type=Path, help="root containing six-digit participant folders")
    ap.add_argument("--participant", action="append", help="six-digit participant ID, repeatable")
    ap.add_argument("--session-root", action="append", help="participant-relative, explicitly reviewed session root")
    ap.add_argument("--game", type=int, help="optional filter; required for --mom/--child")
    ap.add_argument("--mom", type=Path, help="explicit selected mother video (alternative to discovery)")
    ap.add_argument("--child", type=Path, help="explicit selected child video (alternative to discovery)")
    ap.add_argument("--output-root", type=Path, required=True, help="local-only diagnostic output root, never NAS")
    ap.add_argument("--output-prefix", help="reviewed identity prefix for the three filenames")
    ap.add_argument("--max-offset-seconds", type=float, default=30.0,
                    help="provisional post-FFT review limit, in seconds")
    ap.add_argument("--review-policy", type=Path, help="JSON object of acoustic ReviewPolicy settings")
    ap.add_argument("--sample-rate", type=int, default=16000, choices=(8000, 16000),
                    help="September default 16000 Hz; optional 8000 Hz on lower-resource machines")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--ffprobe", default="ffprobe")
    ap.add_argument("--execute", action="store_true", help="generate local diagnostic MP4 (default is plan only)")
    args = ap.parse_args(argv)
    try:
        if args.game is not None and not 1 <= args.game <= 99:
            raise SyncError("game must be in 1..99")
        jobs, issues = plan(args)
        if args.output_prefix and len(jobs) != 1:
            raise SyncError("an explicit filename prefix requires exactly one job")
        policy = ReviewPolicy(**json.loads(args.review_policy.read_text(encoding="utf-8-sig"))) if args.review_policy else ReviewPolicy()
        cfg = json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else {}
        source_tree = (args.source_root if args.source_root else
                       Path(cfg["followup_root"]) / cfg.get("inbox", "00_INBOX")
                       if cfg.get("followup_root") else None)
        outside_input(args.output_root, [j.mom for j in jobs] + [j.child for j in jobs], source_tree)
        if not args.execute:
            print(json.dumps(dict(mode="PLAN_ONLY", jobs=[dict(participant=j.participant, session=j.session,
                game=j.game, mom=str(j.mom), child=str(j.child), output=str(target_folder(args.output_root,j)))
                for j in jobs], issues=issues), indent=2))
            return 0 if jobs else 2
        if not jobs:
            raise SyncError("no unambiguous pair can be processed. " + " | ".join(issues))
        # Diagnostic tool: each job is independent, one failed game cannot silently be a success.
        results = []
        for job in jobs:
            try:
                dest, report = execute_job(job, args.output_root, ffmpeg=args.ffmpeg,
                                           ffprobe=args.ffprobe, sample_rate=args.sample_rate,
                                           output_prefix=args.output_prefix, max_offset_seconds=args.max_offset_seconds,
                                           review_policy=policy)
                results.append(dict(participant=job.participant, session=job.session, game=job.game,
                                    status=report["status"], offset_seconds=report["offset_seconds"],
                                    output_folder=str(dest)))
            except (OSError, ValueError, SyncError, MemoryError) as exc:
                results.append(dict(participant=job.participant, session=job.session, game=job.game,
                                    status="FAILED", detail=str(exc)))
        args.output_root.mkdir(parents=True, exist_ok=True)
        summary = args.output_root / ("sync_report_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                                      + "_" + uuid.uuid4().hex[:6] + ".csv")
        with summary.open("x", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["participant", "session", "game", "status", "offset_seconds", "output_folder", "detail"])
            writer.writeheader()
            writer.writerows(results)
        print(json.dumps(dict(mode="LOCAL_DIAGNOSTIC_ONLY", qc_status="NotApproved",
                              results=results, issues=issues, report=str(summary)), indent=2))
        return 0 if results and all(x["status"] == "CANDIDATE_FOR_MANUAL_QC" for x in results) else 2
    except (OSError, TypeError, ValueError, SyncError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
