#!/usr/bin/env python3
"""Collect reproducible multi-node Stockfish puzzle results."""

import argparse
import csv
import hashlib
import io
import json
import random
import time
from pathlib import Path
from typing import Any

import chess
import chess.engine
import zstandard as zstd


DEFAULT_NODES = [1_000, 3_000, 5_000, 10_000, 20_000, 50_000, 100_000]


def sample_puzzles(dataset: Path, sample_size: int, seed: int) -> list[dict[str, str]]:
    rng = random.Random(seed)
    sample: list[dict[str, str]] = []

    with dataset.open("rb") as fh:
        stream = zstd.ZstdDecompressor().stream_reader(fh)
        text = io.TextIOWrapper(stream, encoding="utf-8")
        reader = csv.DictReader(text)
        valid_count = 0
        for row in reader:
            if not row.get("PuzzleId") or not row.get("FEN") or not row.get("Moves"):
                continue
            valid_count += 1
            if len(sample) < sample_size:
                sample.append(dict(row))
            else:
                replacement = rng.randrange(valid_count)
                if replacement < sample_size:
                    sample[replacement] = dict(row)

    if len(sample) < sample_size:
        raise ValueError(f"Dataset contains only {len(sample)} valid puzzles")
    sample.sort(key=lambda row: row["PuzzleId"])
    return sample


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analyse_move(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    nodes: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    info = engine.analyse(board, chess.engine.Limit(nodes=nodes))
    elapsed_ms = (time.perf_counter() - started) * 1000
    pv = info.get("pv") or []
    return {
        "best_move": pv[0].uci() if pv else None,
        "pv": [move.uci() for move in pv],
        "elapsed_ms": round(elapsed_ms, 3),
        "reported_nodes": info.get("nodes"),
        "depth": info.get("depth"),
        "seldepth": info.get("seldepth"),
        "score": str(info["score"]) if info.get("score") is not None else None,
    }


def collect_engine_results(
    engine: chess.engine.SimpleEngine,
    fen: str,
    moves: list[str],
    nodes_limits: list[int],
) -> dict[str, Any]:
    board = chess.Board(fen)
    board.push_uci(moves[0])
    decisions: list[dict[str, Any]] = []

    for ply, expected in enumerate(moves[1:], start=1):
        decision: dict[str, Any] = {
            "ply_after_setup": ply,
            "fen": board.fen(),
            "expected_move": expected,
            "results": {},
        }
        for nodes in nodes_limits:
            decision["results"][str(nodes)] = analyse_move(engine, board, nodes)
        decisions.append(decision)
        board.push_uci(expected)
    return {"decisions": decisions}


def engine_description(engine: chess.engine.SimpleEngine) -> dict[str, Any]:
    return dict(engine.id)


def parse_nodes(value: str) -> list[int]:
    nodes = sorted({int(item) for item in value.split(",") if item.strip()})
    if not nodes or any(item <= 0 for item in nodes):
        raise argparse.ArgumentTypeError("nodes must be positive comma-separated integers")
    return nodes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/lichess_db_puzzle.csv.zst"))
    parser.add_argument("--engine-custom", type=Path, default=Path("my_custom_stockfish/stockfish"))
    parser.add_argument("--engine-official", type=Path, default=Path("official_stockfish_18/stockfish"))
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--nodes", type=parse_nodes, default=DEFAULT_NODES)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--hash-mb", type=int, default=256)
    parser.add_argument("--output", type=Path, default=Path("results/puzzle_raw_100.json"))
    args = parser.parse_args()

    if args.sample_size <= 0:
        parser.error("--sample-size must be positive")
    if args.threads <= 0 or args.hash_mb <= 0:
        parser.error("--threads and --hash-mb must be positive")

    puzzles = sample_puzzles(args.dataset, args.sample_size, args.seed)
    custom = chess.engine.SimpleEngine.popen_uci(str(args.engine_custom))
    official = chess.engine.SimpleEngine.popen_uci(str(args.engine_official))
    started = time.time()
    try:
        for engine in (custom, official):
            engine.configure({"Threads": args.threads, "Hash": args.hash_mb})

        records = []
        for index, puzzle in enumerate(puzzles, start=1):
            moves = puzzle["Moves"].split()
            record = {
                "metadata": puzzle,
                "moves": moves,
                "custom": collect_engine_results(custom, puzzle["FEN"], moves, args.nodes),
                "official": collect_engine_results(official, puzzle["FEN"], moves, args.nodes),
            }
            records.append(record)
            print(f"processed {index}/{len(puzzles)}", flush=True)

        output = {
            "schema_version": 1,
            "created_at_unix": time.time(),
            "dataset": str(args.dataset),
            "dataset_sha256": sha256_file(args.dataset),
            "sample_size": len(records),
            "seed": args.seed,
            "nodes_limits": args.nodes,
            "threads": args.threads,
            "hash_mb": args.hash_mb,
            "engines": {
                "custom": {
                    "path": str(args.engine_custom),
                    "id": engine_description(custom),
                },
                "official": {
                    "path": str(args.engine_official),
                    "id": engine_description(official),
                },
            },
            "elapsed_seconds": round(time.time() - started, 3),
            "puzzles": records,
        }
    finally:
        custom.quit()
        official.quit()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {args.output}")


if __name__ == "__main__":
    main()
