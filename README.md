# NeuroForge

NeuroForge is a modified [Stockfish 18](https://github.com/official-stockfish/Stockfish)
engine using a self-trained NNUE evaluation network. It is a Stockfish fork, not
an independent search engine: the search and UCI framework are based on Stockfish,
while the evaluation network and selected integration changes are maintained here.

## Features

- Stockfish 18 search framework and UCI interface.
- Custom `HalfKAv2_hm` NNUE architecture:
  `22528 -> 1024 -> 15 -> 32 -> 1`.
- One custom NNUE network (`final_model.nnue`) published openly with the project.
- No opening book is included or required.

The network was trained for approximately 13 epochs on about 1.3 billion
positions. The training data came from a subset of the
[T80 October 2022 best-move dataset](https://www.kaggle.com/datasets/linrock/nn-335a9b2d8a80-t80-oct2022-bestmove),
which is published on Kaggle under CC0/Public Domain terms. The complete 68 GB
dataset is not included in this repository.

## Build

The modified Stockfish source is in [`Stockfish-sf_18/`](Stockfish-sf_18/).
On a Unix-like system:

```bash
cd Stockfish-sf_18/src
make -j profile-build
```

The build expects `final_model.nnue` in the source directory. Copy the published
network there before building, or pass its path through the UCI `EvalFile` option.

The resulting executable is a UCI engine and can be used with a chess GUI or
the Lichess bot framework. Typical settings used for NeuroForge testing were
one search thread and a 256 MB hash table; these are runtime settings, not
requirements of the engine.

## Puzzle benchmark

The benchmark scripts are:

- [`puzzle_collect.py`](puzzle_collect.py): runs the custom and reference
  engines and stores raw results;
- [`puzzle_metrics.py`](puzzle_metrics.py): recalculates metrics without
  running the engines again;
- [`measure_puzzle_lengths.py`](measure_puzzle_lengths.py): measures line
  lengths for planning a benchmark.

The published 10,000-puzzle summary is in
[`results/puzzle_metrics.csv`](results/puzzle_metrics.csv). It used one thread,
256 MB hash, and node limits from 1,000 through 100,000. The reference binary
was official Stockfish 18; it is not redistributed here.

At 100,000 nodes:

| Engine | First-move accuracy | Full-line accuracy | Fully solved |
| --- | ---: | ---: | ---: |
| NeuroForge custom NNUE | 99.34% | 81.20% | 7,743 / 10,000 |
| Official Stockfish 18 | 99.52% | 81.19% | 7,771 / 10,000 |

Puzzle accuracy is not an Elo estimate. Results depend on the dataset,
position sampling, node/time limit, hardware, engine options, and metric
definition. Full-line accuracy here evaluates only the puzzle side's moves and
stops at the first mismatch.

## Repository layout

```text
Stockfish-sf_18/       Modified Stockfish 18 source
final_model.nnue       Custom NNUE network
results/               Reproducible benchmark summaries
puzzle_*.py            Benchmark collection and metric scripts
```

The Lichess bot, virtual environment, large datasets, checkpoints, reference
binary, and raw 319 MB benchmark capture are intentionally kept out of the
public source repository. They are local artifacts or can be reproduced from
the documented inputs.

## Licensing

The modified Stockfish source and source-level changes are distributed under
the [GNU General Public License v3.0](Stockfish-sf_18/Copying.txt), consistent
with the upstream Stockfish project. Copyright and attribution notices in the
Stockfish source must be preserved.

The custom NNUE network is distributed together with this project under GPLv3
as part of the engine distribution. Dataset licensing is separate: the source
training dataset is identified above as CC0/Public Domain according to its
Kaggle listing. See [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).

## Disclaimer

NeuroForge is an independent project and is not an official Stockfish release.
Stockfish is a registered trademark of the Stockfish developers where
applicable.
