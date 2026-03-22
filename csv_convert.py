#!/usr/bin/env python3
"""
Convert OU admissions CSV (University, OUAC Code, Program name, Top 6 Average)
to JSON: one entry per (university, program code) with all listed top-6 averages
and their arithmetic mean.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RowLoadStats:
    total_rows: int
    accepted: int
    skipped_empty_average: int
    skipped_invalid_average: int

    @property
    def skipped_total(self) -> int:
        return self.skipped_empty_average + self.skipped_invalid_average


def load_grouped_averages(csv_path: Path) -> tuple[dict[tuple[str, str], list[float]], RowLoadStats]:
    """Group Top 6 Average values by (University, OUAC Code)."""
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    skipped_empty = 0
    skipped_invalid = 0
    accepted = 0
    total_rows = 0
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1
            uni = (row.get("University") or "").strip()
            code = (row.get("OUAC Code") or "").strip()
            raw = (row.get("Top 6 Average") or "").strip()
            if not raw:
                skipped_empty += 1
                continue
            try:
                avg = float(raw)
            except ValueError:
                skipped_invalid += 1
                continue
            accepted += 1
            groups[(uni, code)].append(avg)
    stats = RowLoadStats(
        total_rows=total_rows,
        accepted=accepted,
        skipped_empty_average=skipped_empty,
        skipped_invalid_average=skipped_invalid,
    )
    return groups, stats


def build_records(groups: dict[tuple[str, str], list[float]]) -> list[dict]:
    records = []
    for (university, ouac_code), averages in sorted(groups.items()):
        mean_val = statistics.mean(averages)
        records.append(
            {
                "university": university,
                "program_code": ouac_code,
                "top_6_averages": averages,
                "average": round(mean_val, 4),
            }
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=Path("resources/24_25_data.csv"),
        help="Input CSV path",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("reddit_programs_24_25.json"),
        help="Output JSON path (default: ./reddit_programs_24_25.json)",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    groups, row_stats = load_grouped_averages(args.input)
    records = build_records(groups)
    payload = {"programs": records}

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote {len(records)} program groups to {args.output}")
    print(
        f"CSV rows: {row_stats.total_rows}, "
        f"used: {row_stats.accepted}, "
        f"skipped: {row_stats.skipped_total} "
        f"(empty Top 6: {row_stats.skipped_empty_average}, "
        f"invalid: {row_stats.skipped_invalid_average})",
    )


if __name__ == "__main__":
    main()
