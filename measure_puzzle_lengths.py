#!/usr/bin/env python3
"""Measure full-line lengths for a reproducible random puzzle sample."""

import argparse
import csv
import io
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

import zstandard as zstd


def sample_puzzles(
    dataset: Path, sample_size: int, seed: int
) -> list[dict[str, str]]:
    rng = random.Random(seed)
    sample: list[dict[str, str]] = []
    valid_count = 0

    with dataset.open("rb") as fh:
        stream = zstd.ZstdDecompressor().stream_reader(fh)
        text = io.TextIOWrapper(stream, encoding="utf-8")
        for row in csv.DictReader(text):
            if not row.get("PuzzleId") or not row.get("Moves"):
                continue

            valid_count += 1
            if len(sample) < sample_size:
                sample.append(dict(row))
                continue

            replacement = rng.randrange(valid_count)
            if replacement < sample_size:
                sample[replacement] = dict(row)

    if len(sample) < sample_size:
        raise ValueError(f"Dataset contains only {len(sample)} valid puzzles")
    sample.sort(key=lambda row: row["PuzzleId"])
    return sample


def measure(puzzles: list[dict[str, str]]) -> dict[str, Any]:
    lengths = [len(puzzle["Moves"].split()) - 1 for puzzle in puzzles]
    counts = Counter(lengths)
    ordered_lengths = sorted(lengths)

    def percentile(percent: float) -> int:
        index = min(
            len(ordered_lengths) - 1,
            int((percent / 100) * len(ordered_lengths)),
        )
        return ordered_lengths[index]

    rows = [
        {
            "PuzzleId": puzzle["PuzzleId"],
            "full_line_plies": len(puzzle["Moves"].split()) - 1,
            "rating": puzzle.get("Rating"),
            "themes": puzzle.get("Themes"),
        }
        for puzzle in puzzles
    ]
    return {
        "puzzles": len(puzzles),
        "full_line_plies": {
            "min": min(lengths),
            "max": max(lengths),
            "mean": sum(lengths) / len(lengths),
            "median": percentile(50),
            "p90": percentile(90),
            "p95": percentile(95),
            "p99": percentile(99),
            "total": sum(lengths),
        },
        "distribution": {
            str(length): counts[length] for length in sorted(counts)
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=Path("data/lichess_db_puzzle.csv.zst")
    )
    parser.add_argument("--sample-size", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument(
        "--output", type=Path, default=Path("results/puzzle_lengths_10000.json")
    )
    args = parser.parse_args()

    if args.sample_size <= 0:
        parser.error("--sample-size must be positive")

    puzzles = sample_puzzles(args.dataset, args.sample_size, args.seed)
    result = {
        "schema_version": 1,
        "dataset": str(args.dataset),
        "sample_size": args.sample_size,
        "seed": args.seed,
        "full_line_definition": "number of solution-side plies after the setup move",
        **measure(puzzles),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    csv_path = args.output.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=result["rows"][0].keys())
        writer.writeheader()
        writer.writerows(result["rows"])

    stats = result["full_line_plies"]
    print(f"sampled puzzles: {result['puzzles']}")
    print(
        "full-line plies: "
        f"min={stats['min']}, mean={stats['mean']:.2f}, "
        f"median={stats['median']}, p95={stats['p95']}, max={stats['max']}"
    )
    print(f"total solution-side plies: {stats['total']}")
    print(f"saved {args.output}")
    print(f"saved {csv_path}")


if __name__ == "__main__":
    main()
