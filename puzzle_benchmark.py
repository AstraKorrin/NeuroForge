#!/usr/bin/env python3
import argparse
import csv
import io
import json
import time
from pathlib import Path

import chess
import chess.engine
import zstandard as zstd


def iter_puzzles(path: str, limit: int | None = None):
    with open(path, "rb") as fh:
        dctx = zstd.ZstdDecompressor()
        stream = dctx.stream_reader(fh)
        text = io.TextIOWrapper(stream, encoding="utf-8")
        reader = csv.reader(text)
        try:
            header = next(reader)
        except StopIteration:
            return

        for idx, row in enumerate(reader):
            if limit is not None and idx >= limit:
                break
            if len(row) < 3:
                continue
            puzzle_id, fen, moves_str = row[0], row[1], row[2]
            if not fen or not moves_str:
                continue
            yield puzzle_id, fen, moves_str.split()


def configure_engine(engine, threads: int = 2, hash_mb: int = 256):
    try:
        engine.configure({"Threads": threads, "Hash": hash_mb})
    except Exception:
        pass


def analyse_best_move(engine, board, nodes: int):
    info = engine.analyse(board, chess.engine.Limit(nodes=nodes))
    pv = info.get("pv")
    if not pv:
        return None
    return pv[0].uci()


def evaluate_puzzle(engine, puzzle_id, fen, moves, nodes_per_move: int):
    board = chess.Board(fen)
    if len(moves) < 2:
        return {
            "puzzle_id": puzzle_id,
            "fen": fen,
            "first_move_ok": False,
            "first_move_expected": None,
            "first_move_actual": None,
            "full_correct_moves": 0,
            "total_expected_moves": 0,
            "first_move_index": 0,
        }

    board.push_uci(moves[0])
    expected_first = moves[1]
    actual_first = analyse_best_move(engine, board, nodes_per_move)
    first_ok = actual_first == expected_first

    board_after_first = board.copy()
    matched = 0
    total_expected = len(moves) - 1
    for expected in moves[1:]:
        if board_after_first.is_game_over(claim_draw=True):
            break
        actual = analyse_best_move(engine, board_after_first, nodes_per_move)
        if actual == expected:
            board_after_first.push_uci(expected)
            matched += 1
        else:
            break

    return {
        "puzzle_id": puzzle_id,
        "fen": fen,
        "first_move_ok": first_ok,
        "first_move_expected": expected_first,
        "first_move_actual": actual_first,
        "full_correct_moves": matched,
        "total_expected_moves": total_expected,
    }


def run_benchmark(engine_a: str, engine_b: str, dataset: str, limit: int, nodes: int, threads: int, hash_mb: int, out_dir: str):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    eng_a = chess.engine.SimpleEngine.popen_uci(engine_a)
    eng_b = chess.engine.SimpleEngine.popen_uci(engine_b)
    configure_engine(eng_a, threads=threads, hash_mb=hash_mb)
    configure_engine(eng_b, threads=threads, hash_mb=hash_mb)

    try:
        results = {
            "engine_a": engine_a,
            "engine_b": engine_b,
            "dataset": dataset,
            "limit": limit,
            "nodes_per_move": nodes,
            "threads": threads,
            "hash_mb": hash_mb,
            "start_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "puzzles": [],
        }

        for puzzle_id, fen, moves in iter_puzzles(dataset, limit):
            rec_a = evaluate_puzzle(eng_a, puzzle_id, fen, moves, nodes)
            rec_b = evaluate_puzzle(eng_b, puzzle_id, fen, moves, nodes)
            results["puzzles"].append({
                "puzzle_id": puzzle_id,
                "fen": fen,
                "moves": moves,
                "engine_a": rec_a,
                "engine_b": rec_b,
            })

        summary = {
            "engine_a": engine_a,
            "engine_b": engine_b,
            "dataset": dataset,
            "limit": limit,
            "nodes_per_move": nodes,
            "threads": threads,
            "hash_mb": hash_mb,
            "start_time": results["start_time"],
            "end_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_puzzles": len(results["puzzles"]),
            "engine_a_first_accuracy": None,
            "engine_b_first_accuracy": None,
            "engine_a_full_accuracy": None,
            "engine_b_full_accuracy": None,
        }

        def compute_first_accuracy(engine_key):
            n = 0
            good = 0
            for item in results["puzzles"]:
                rec = item[engine_key]
                if rec["first_move_expected"] is None:
                    continue
                n += 1
                good += int(rec["first_move_ok"])
            return (good / n) if n else 0.0

        def compute_full_accuracy(engine_key):
            total_expected = 0
            total_matched = 0
            for item in results["puzzles"]:
                rec = item[engine_key]
                total_expected += rec["total_expected_moves"]
                total_matched += rec["full_correct_moves"]
            return (total_matched / total_expected) if total_expected else 0.0

        summary["engine_a_first_accuracy"] = compute_first_accuracy("engine_a")
        summary["engine_b_first_accuracy"] = compute_first_accuracy("engine_b")
        summary["engine_a_full_accuracy"] = compute_full_accuracy("engine_a")
        summary["engine_b_full_accuracy"] = compute_full_accuracy("engine_b")

        output_base = out_dir / f"puzzle_benchmark_limit{limit}_nodes{nodes}"
        json_path = output_base.with_suffix(".json")
        csv_path = output_base.with_suffix(".csv")

        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump({**summary, "puzzles": results["puzzles"]}, fh, ensure_ascii=False, indent=2)

        fieldnames = [
            "puzzle_id",
            "engine_a_first_move_ok",
            "engine_a_first_move_expected",
            "engine_a_first_move_actual",
            "engine_a_full_correct_moves",
            "engine_a_total_expected_moves",
            "engine_b_first_move_ok",
            "engine_b_first_move_expected",
            "engine_b_first_move_actual",
            "engine_b_full_correct_moves",
            "engine_b_total_expected_moves",
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for item in results["puzzles"]:
                rec_a = item["engine_a"]
                rec_b = item["engine_b"]
                writer.writerow({
                    "puzzle_id": item["puzzle_id"],
                    "engine_a_first_move_ok": int(rec_a["first_move_ok"]),
                    "engine_a_first_move_expected": rec_a["first_move_expected"],
                    "engine_a_first_move_actual": rec_a["first_move_actual"],
                    "engine_a_full_correct_moves": rec_a["full_correct_moves"],
                    "engine_a_total_expected_moves": rec_a["total_expected_moves"],
                    "engine_b_first_move_ok": int(rec_b["first_move_ok"]),
                    "engine_b_first_move_expected": rec_b["first_move_expected"],
                    "engine_b_first_move_actual": rec_b["first_move_actual"],
                    "engine_b_full_correct_moves": rec_b["full_correct_moves"],
                    "engine_b_total_expected_moves": rec_b["total_expected_moves"],
                })

        print(json.dumps({
            "summary": summary,
            "json_path": str(json_path),
            "csv_path": str(csv_path),
        }, ensure_ascii=False, indent=2))
    finally:
        eng_a.quit()
        eng_b.quit()


def parse_args():
    parser = argparse.ArgumentParser(description="Benchmark a custom NNUE build against official Stockfish on Lichess puzzles.")
    parser.add_argument("--dataset", default="/home/tenzin/Code/ChessEngine/data/lichess_db_puzzle.csv.zst")
    parser.add_argument("--engine-a", default="/home/tenzin/Code/ChessEngine/Stockfish-sf_18/src/stockfish")
    parser.add_argument("--engine-b", default="/tmp/stockfish18-official/stockfish/stockfish-ubuntu-x86-64-avx2")
    parser.add_argument("--limit", type=int, default=1000, help="Number of puzzle rows to process. Set to 0 for all rows.")
    parser.add_argument("--nodes", type=int, default=50000, help="Fixed node budget per move.")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--hash-mb", type=int, default=256)
    parser.add_argument("--out-dir", default="/home/tenzin/Code/ChessEngine/results")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_benchmark(
        engine_a=args.engine_a,
        engine_b=args.engine_b,
        dataset=args.dataset,
        limit=args.limit,
        nodes=args.nodes,
        threads=args.threads,
        hash_mb=args.hash_mb,
        out_dir=args.out_dir,
    )
