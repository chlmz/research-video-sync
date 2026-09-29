#!/usr/bin/env python3
"""RG2019 follow-up video synchronisation pipeline (v2) - command-line entry point.

    python pipeline_rg2019.py --config config.json --dry-run
    python pipeline_rg2019.py --config config.json

Exit codes: 0 = finished, nothing needs a human;  2 = finished, but some participants need
manual review or failed;  3 = configuration / tooling / lock problem (nothing was processed).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from rg2019 import __version__, config as cfgmod, media
from rg2019.pipeline import Pipeline
from rg2019.state import RunLock

log = logging.getLogger("rg2019")


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="RG2019 INBOX -> RAW -> SYNCED pipeline")
    ap.add_argument("--config", required=True, type=Path, help="path to config.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what WOULD happen; moves nothing, writes no state, encodes nothing")
    ap.add_argument("--participant", action="append", metavar="ID",
                    help="only handle this participant (repeatable)")
    ap.add_argument("--reprocess", action="append", metavar="ID",
                    help="recompute this participant from RAW; previous outputs are archived, not deleted")
    ap.add_argument("--manual-offset", type=float, metavar="SECONDS",
                    help="with exactly one --participant: use this reviewed offset (>0 trims mom, <0 trims child)")
    ap.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO"])
    ap.add_argument("--version", action="version", version=f"pipeline_rg2019 {__version__}")
    return ap.parse_args(argv)


def setup_logging(level: str, log_dir: Path | None) -> None:
    root = logging.getLogger("rg2019")
    root.handlers.clear()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    if sys.stdout is not None:                       # None under pythonw.exe / some schedulers
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / f"pipeline_{datetime.now():%Y-%m-%d}.log", encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        cfg = cfgmod.load(args.config)
    except cfgmod.ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 3
    if args.manual_offset is not None and not (args.participant and len(args.participant) == 1):
        print("CONFIG ERROR: --manual-offset requires exactly one --participant", file=sys.stderr)
        return 3
    setup_logging(args.log_level, None if args.dry_run else cfg.log_file_dir if cfg.followup_root.is_dir() else None)

    if not cfg.followup_root.is_dir():
        log.error("followup_root does not exist: %s", cfg.followup_root)
        return 3
    if not cfg.inbox_dir.is_dir():
        log.error("inbox folder does not exist: %s", cfg.inbox_dir)
        return 3
    try:
        versions = media.check_tools(cfg)
    except media.MediaError as exc:
        log.error("%s", exc)
        return 3
    log.info("pipeline_rg2019 %s | root=%s | dry_run=%s", __version__, cfg.followup_root, args.dry_run)
    for exe, v in versions.items():
        log.info("%s: %s", exe, v)

    pipe = Pipeline(cfg, dry_run=args.dry_run, only=args.participant, reprocess=args.reprocess,
                    manual_offset=args.manual_offset)
    if args.dry_run:
        summary = pipe.run()
    else:
        for d in (cfg.raw_dir, cfg.synced_dir, cfg.logs_dir):
            d.mkdir(parents=True, exist_ok=True)
        try:
            with RunLock(cfg.lock_file, cfg.lock_stale_hours):
                summary = pipe.run()
        except RuntimeError as exc:
            log.error("%s", exc)
            return 3
    text = summary.render()
    for line in text.splitlines():
        log.info("%s", line)
    return summary.exit_code()


if __name__ == "__main__":
    sys.exit(main())
