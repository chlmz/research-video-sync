"""Per-participant state files, the master CSV and the run lock.

State lives ONLY under 99_LOGS_QC (never in 01_RAW).  All writes are atomic
(write temp file in the same folder, then os.replace)."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import Config

SCHEMA = 1
HISTORY_LIMIT = 30

CSV_COLUMNS = ["participant_id", "status", "mom_source", "child_source", "mom_sha256", "child_sha256",
               "mom_duration", "child_duration", "offset_seconds", "sync_confidence",
               "raw_promoted_at", "sync_completed_at", "last_checked_at", "error_message"]


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def new_state(pid: str, now: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "participant_id": pid, "status": None, "message": "", "stage": "NEW",
            "first_seen_at": now, "last_checked_at": now, "raw_promoted_at": None,
            "sync_completed_at": None, "attempts": 0, "sources": {}, "promotion": {}, "sync": {},
            "outputs": {"files": {}}, "stability": {}, "history": []}


class StateStore:
    def __init__(self, cfg: Config):
        self.dir = cfg.state_dir
        self.csv = cfg.status_csv

    def path(self, pid: str) -> Path:
        return self.dir / f"{pid}.json"

    def load(self, pid: str, now: str) -> dict[str, Any]:
        p = self.path(pid)
        if not p.exists():
            return new_state(pid, now)
        try:
            st = json.loads(p.read_text(encoding="utf-8"))
            if st.get("participant_id") != pid:
                raise ValueError("participant_id mismatch")
            return st
        except (OSError, ValueError) as exc:
            bad = p.with_name(p.name + f".corrupt-{now.replace(':', '')}")
            os.replace(p, bad)
            st = new_state(pid, now)
            st["history"].append({"at": now, "event": f"corrupt state file moved to {bad.name}: {exc}"})
            return st

    def save(self, st: dict[str, Any]) -> None:
        st["history"] = st.get("history", [])[-HISTORY_LIMIT:]
        atomic_write_text(self.path(st["participant_id"]),
                          json.dumps(st, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    def all_ids(self) -> list[str]:
        return sorted(p.stem for p in self.dir.glob("*.json")) if self.dir.exists() else []

    def rewrite_csv(self) -> None:
        """Regenerate the human-readable master CSV from the state files (one row per participant,
        so running the pipeline many times can never create duplicate rows)."""
        rows = []
        for pid in self.all_ids():
            try:
                st = json.loads(self.path(pid).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            src, sync = st.get("sources", {}), st.get("sync", {})
            mom, child = src.get("mom", {}), src.get("child", {})
            rows.append({
                "participant_id": pid, "status": st.get("status"),
                "mom_source": mom.get("name", ""), "child_source": child.get("name", ""),
                "mom_sha256": mom.get("sha256", ""), "child_sha256": child.get("sha256", ""),
                "mom_duration": _fmt(mom.get("media", {}).get("duration")),
                "child_duration": _fmt(child.get("media", {}).get("duration")),
                "offset_seconds": _fmt(sync.get("offset_seconds"), 4),
                "sync_confidence": _fmt(sync.get("confidence"), 3),
                "raw_promoted_at": st.get("raw_promoted_at") or "",
                "sync_completed_at": st.get("sync_completed_at") or "",
                "last_checked_at": st.get("last_checked_at") or "",
                "error_message": st.get("message") if st.get("status") != "SUCCESS" else ""})
        import io
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)
        atomic_write_text(self.csv, buf.getvalue())


def _fmt(v, nd=2):
    return "" if v is None else (f"{v:.{nd}f}" if isinstance(v, (int, float)) else str(v))


class RunLock:
    """Prevents two daily runs from overlapping (e.g. a long run + the next scheduled trigger)."""

    def __init__(self, path: Path, stale_hours: float):
        self.path, self.stale = path, timedelta(hours=stale_hours)
        self.held = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                age = datetime.now() - datetime.fromtimestamp(self.path.stat().st_mtime)
                if age < self.stale:
                    raise RuntimeError(f"another pipeline run appears to be active (lock {self.path}, "
                                       f"age {age}); if it crashed, delete the lock file")
                self.path.unlink(missing_ok=True)   # stale lock from a crashed run
                continue
            with os.fdopen(fd, "w") as fh:
                fh.write(f"pid={os.getpid()} started={datetime.now().isoformat(timespec='seconds')}\n")
            self.held = True
            return
        raise RuntimeError(f"could not acquire lock {self.path}")

    def release(self) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)
            self.held = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
