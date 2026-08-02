#!/bin/bash
# Paired Claude Opus 4.7 <-> OpenAI gpt-5.5 analysis, from the released
# prediction logs. Does NOT re-run inference. Cost: $0. Time: under a minute.
#
# This is the script cited in §4 of the paper for the released prediction logs.
#
#   bash examples/reproduce_paired.sh
#
# PRED_DIR defaults to <repo>/predictions; point it at the predictions/
# directory of the released dataset if you keep them apart:
#
#   PRED_DIR=/path/to/dataset/predictions bash examples/reproduce_paired.sh

set -euo pipefail

REPO_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
PRED_DIR="${PRED_DIR:-$REPO_ROOT/predictions}"

if [ ! -d "$PRED_DIR" ]; then
    echo "ERROR: PRED_DIR=$PRED_DIR not found." >&2
    echo "  Point PRED_DIR at the predictions/ directory of the released" >&2
    echo "  dataset, or run examples/reproduce_table3.sh first." >&2
    exit 1
fi

mkdir -p "$REPO_ROOT/analysis_repro"

echo "[1/2] Paired Opus <-> gpt-5.5, nine sub-tasks"
python "$REPO_ROOT/eval/paired_frontier_analysis.py" \
  --opus "$PRED_DIR/frontier/claude_opus_main.jsonl" \
  --gpt5 "$PRED_DIR/frontier/gpt-5.5_main_paired.jsonl" \
  --output "$REPO_ROOT/analysis_repro/paired_opus_gpt55.json" \
  --name-a Opus --name-b GPT-5.5

echo "[2/2] Paired A1-v2 (section-only)"
python "$REPO_ROOT/eval/paired_frontier_analysis.py" \
  --opus "$PRED_DIR/frontier/claude_opus_a1_section_only.jsonl" \
  --gpt5 "$PRED_DIR/frontier/gpt-5.5_a1_v2_paired.jsonl" \
  --output "$REPO_ROOT/analysis_repro/paired_opus_gpt55_a1_v2.json" \
  --name-a Opus --name-b GPT-5.5

echo
echo "Done. Outputs in analysis_repro/; compare against the released"
echo "analysis/paired_opus_gpt55_final.json and paired_opus_gpt55_a1_v2.json."
