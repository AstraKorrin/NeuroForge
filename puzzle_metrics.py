#!/usr/bin/env python3
"""Compute puzzle metrics from raw multi-node benchmark results."""

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def calculate(records: list[dict[str, Any]], engine_name: str, nodes: int) -> dict[str, Any]:
    first_total = first_correct = matched = expected_total = solved = 0
    for puzzle in records:
        decisions = puzzle[engine_name]["decisions"]
        if not decisions:
            continue
        first_total += 1
        expected_total += len(decisions)
        first_correct += decisions[0]["results"][str(nodes)]["best_move"] == decisions[0]["expected_move"]
        run_matched = 0
        for decision in decisions:
            if decision["results"][str(nodes)]["best_move"] != decision["expected_move"]:
                break
            run_matched += 1
        matched += run_matched
        solved += run_matched == len(decisions)

    return {
        "engine": engine_name,
        "nodes": nodes,
        "puzzles": first_total,
        "first_move_accuracy": first_correct / first_total if first_total else 0.0,
        "full_line_accuracy": matched / expected_total if expected_total else 0.0,
        "solved_puzzles": solved,
        "solved_rate": solved / first_total if first_total else 0.0,
        "matched_moves": matched,
        "expected_moves": expected_total,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    raw = json.loads(args.input.read_text(encoding="utf-8"))
    rows = [
        calculate(raw["puzzles"], engine, nodes)
        for nodes in raw["nodes_limits"]
        for engine in ("custom", "official")
    ]
    output = {
        "schema_version": 1,
        "source": str(args.input),
        "nodes_limits": raw["nodes_limits"],
        "metrics": rows,
    }
    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        csv_path = args.output.with_suffix(".csv")
    else:
        print(text)
        return

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"saved {args.output}")
    print(f"saved {csv_path}")


if __name__ == "__main__":
    main()
