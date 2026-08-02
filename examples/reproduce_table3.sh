#!/bin/bash
# Reproduce paper Table 3 (zero-shot accuracy on the nine ShipBench sub-tasks).
#
#   bash examples/reproduce_table3.sh
#       Scores the released prediction logs with eval/eval_canonical.py.
#       No API key, no cost, ~1 minute.
#
#   bash examples/reproduce_table3.sh --rerun-inference
#       Re-runs the two frontier systems first, then scores the new logs.
#       Requires ANTHROPIC_API_KEY and OPENAI_API_KEY. ~2 hours, ~$200.
#       Open-weight rows are not re-run here; see README for those commands.
#
# SHIPBENCH_ROOT must point at the dataset root containing task_files/ and
# predictions/.

set -euo pipefail

if [ -z "${SHIPBENCH_ROOT:-}" ]; then
    echo "ERROR: SHIPBENCH_ROOT not set. Point it at the dataset root" >&2
    echo "       (the directory containing task_files/ and predictions/)." >&2
    exit 1
fi

REPO_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
RERUN=0
[ "${1:-}" = "--rerun-inference" ] && RERUN=1

PRED_DIR="$SHIPBENCH_ROOT/predictions"

if [ "$RERUN" = "1" ]; then
    : "${ANTHROPIC_API_KEY:?ERROR: ANTHROPIC_API_KEY not set}"
    : "${OPENAI_API_KEY:?ERROR: OPENAI_API_KEY not set}"

    PRED_DIR="$REPO_ROOT/predictions_repro"
    mkdir -p "$PRED_DIR/frontier"

    echo "[1/3] Claude Opus 4.7 inference (~30 min, ~\$80)"
    python "$REPO_ROOT/inference/run_frontier_v3.py" \
      --task-file "$SHIPBENCH_ROOT/task_files/task_main_eval_opus_paired.jsonl" \
      --output    "$PRED_DIR/frontier/claude_opus_main.jsonl" \
      --n-per-task 200 --max-tokens 1024 --seed 42

    echo "[2/3] OpenAI gpt-5.5 inference (~1.5 h, ~\$170)"
    python "$REPO_ROOT/inference/run_frontier_openai.py" \
      --task-file "$SHIPBENCH_ROOT/task_files/task_main_eval_opus_paired.jsonl" \
      --output    "$PRED_DIR/frontier/gpt-5.5_main_paired.jsonl" \
      --model gpt-5.5 --n-per-task 200 --max-tokens 8192 \
      --reasoning-effort medium --concurrency 16 --seed 42

    echo "NOTE: open-weight rows are read from the released logs; re-running"
    echo "      them needs a GPU (see README)."
    cp -r "$SHIPBENCH_ROOT/predictions/open_weight" "$PRED_DIR/" 2>/dev/null || true
    STEP=3
else
    STEP=1
fi

mkdir -p "$REPO_ROOT/analysis_repro"

echo "[$STEP/$STEP] Scoring with the canonical evaluator"
python "$REPO_ROOT/eval/build_table3.py" \
  --root "$SHIPBENCH_ROOT" \
  --predictions-dir "$PRED_DIR" \
  --output "$REPO_ROOT/analysis_repro/table3.json"

echo
echo "Paired statistics (bootstrap CI, McNemar, Clopper-Pearson):"
python "$REPO_ROOT/eval/paired_frontier_analysis.py" \
  --opus "$PRED_DIR/frontier/claude_opus_main.jsonl" \
  --gpt5 "$PRED_DIR/frontier/gpt-5.5_main_paired.jsonl" \
  --output "$REPO_ROOT/analysis_repro/paired_opus_gpt55.json" \
  --name-a Opus --name-b GPT-5.5

echo
echo "Done. Table 3 written to analysis_repro/table3.json"
