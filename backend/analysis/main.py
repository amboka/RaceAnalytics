#!/usr/bin/env python3
"""Entry point to generate lap time JSON reports.

Default behavior writes full-track slow/fast comparison to analysis/lap_times.json.
You can optionally request a specific segment.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from lapTime import compute_lap_times


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate lap time JSON report")
    parser.add_argument(
        "--segment",
        type=str,
        default=None,
        help="Optional segment name (example: snake, long, corner). Default is full track.",
    )
    parser.add_argument(
        "--start-ns",
        type=int,
        default=None,
        help="Optional start timestamp in ns.",
    )
    parser.add_argument(
        "--end-ns",
        type=int,
        default=None,
        help="Optional end timestamp in ns.",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default=str(Path(__file__).resolve().parent / "lap_times.json"),
        help="Output JSON file path. Defaults to analysis/lap_times.json.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    compute_lap_times(
        segment=args.segment,
        start_ns=args.start_ns,
        end_ns=args.end_ns,
        output_file=args.output_file,
    )
    print(f"Wrote lap-time report to {args.output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
