"""Read-only field inventory CLI; JSON goes to stdout, never into study folders."""
import argparse
import json
from pathlib import Path

from rg2019.config import load
from rg2019.discovery import discover_field


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--participant', required=True)
    args = parser.parse_args()
    report = discover_field(load(args.config), args.participant)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
