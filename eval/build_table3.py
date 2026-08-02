#!/usr/bin/env python3
"""
Assemble Table 3 (zero-shot accuracy on the nine ShipBench sub-tasks) from
prediction logs, using eval_canonical.py for every cell.

Source mapping. Eight of the nine columns are scored from each model's
`*_main.jsonl` log. The A1 column is not: Table 3 reports the **section-only
v2** reformulation of A1 (Pitfall 7, App. K), so it is scored from the
`*_a1v2.jsonl` / `*_a1_section_only.jsonl` logs. The `A1_shiptype` task that
still appears inside `*_main.jsonl` is the superseded two-view v1 and is not
what Table 3 prints.

Usage:
    python eval/build_table3.py --root <SHIPBENCH_ROOT>
    python eval/build_table3.py --root <SHIPBENCH_ROOT> --predictions-dir ./predictions_repro
    python eval/build_table3.py --root <SHIPBENCH_ROOT> --latex
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_canonical as EC  # noqa: E402

COLUMNS = [
    ("A1_shiptype_section_only", "A1-stype"),
    ("A2_stiffener_type",        "A2-stype"),
    ("B1_plate_thickness",       "B1-plate"),
    ("B2_stiffener_size",        "B2-size"),
    ("B3_cargo_capacity_v1",     "B3-cargo"),
    ("B4_section_area_v1",       "B4-area"),
    ("C1_compartment_locate",    "C1-cmp-loc"),
    ("C2_compartment_boundary",  "C2-cmp-bnd"),
    ("C3_bulkhead_position",     "C3-bulk"),
]

# (display name, main log, A1-v2 log)
ROWS = [
    ("Qwen3-VL-8B",     "open_weight/zeroshot/qwen3vl_main.jsonl",
                        "open_weight/zeroshot/qwen3vl_a1v2.jsonl"),
    ("Qwen2.5-VL-7B",   "open_weight/zeroshot/qwen25vl_main.jsonl",
                        "open_weight/zeroshot/qwen25vl_a1v2.jsonl"),
    ("InternVL3-8B",    "open_weight/zeroshot/internvl3_main.jsonl",
                        "open_weight/zeroshot/internvl3_a1v2.jsonl"),
    ("LLaVA-OV-7B",     "open_weight/zeroshot/llavaov_main.jsonl",
                        "open_weight/zeroshot/llavaov_a1v2.jsonl"),
    ("Claude Opus 4.7", "frontier/claude_opus_main.jsonl",
                        "frontier/claude_opus_a1_section_only.jsonl"),
    ("OpenAI gpt-5.5",  "frontier/gpt-5.5_main_paired.jsonl",
                        "frontier/gpt-5.5_a1_v2_paired.jsonl"),
]


def score(path, task, gt):
    if not os.path.exists(path):
        return None, 0
    n = c = 0
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("task") != task:
                continue
            item = gt.get(r.get("qa_id"))
            if item is None:
                continue
            n += 1
            c += EC.grade(r.get("prediction", ""), item)["correct"]
    return (100.0 * c / n if n else None), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True,
                    help="dataset root containing task_files/ and predictions/")
    ap.add_argument("--predictions-dir", default=None,
                    help="override the predictions/ location (e.g. a re-run)")
    ap.add_argument("--latex", action="store_true")
    ap.add_argument("--output", default=None)
    a = ap.parse_args()

    gt = EC.load_ground_truth(os.path.join(a.root, "task_files"))
    pred_root = a.predictions_dir or os.path.join(a.root, "predictions")

    grid, counts = {}, {}
    for name, main_log, a1_log in ROWS:
        for task, _ in COLUMNS:
            log = a1_log if task.startswith("A1") else main_log
            acc, n = score(os.path.join(pred_root, log), task, gt)
            grid[(name, task)] = acc
            counts[(name, task)] = n

    hdr = "%-17s" % "Model" + "".join("%11s" % lbl for _, lbl in COLUMNS)
    print()
    print("Table 3: zero-shot accuracy (%) -- scored by eval_canonical.py")
    print(hdr)
    print("-" * len(hdr))
    for name, _, _ in ROWS:
        cells = "".join(
            ("%11s" % "n/a") if grid[(name, t)] is None else ("%11.1f" % grid[(name, t)])
            for t, _ in COLUMNS)
        print("%-17s%s" % (name, cells))
    print()
    print("%-17s%s" % ("n per cell", "".join(
        "%11d" % counts[(ROWS[-1][0], t)] for t, _ in COLUMNS)) + "   (gpt-5.5 row)")

    if a.latex:
        print()
        for name, _, _ in ROWS:
            cells = " & ".join("--" if grid[(name, t)] is None
                               else "%.1f" % grid[(name, t)] for t, _ in COLUMNS)
            print("%s & %s \\\\" % (name, cells))

    if a.output:
        os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
        payload = {"table": "3", "evaluator": "eval_canonical.py",
                   "cells": {"%s|%s" % (m, t): grid[(m, t)]
                             for m, _, _ in ROWS for t, _ in COLUMNS},
                   "n": {"%s|%s" % (m, t): counts[(m, t)]
                         for m, _, _ in ROWS for t, _ in COLUMNS}}
        with io.open(a.output, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print("\nSaved: %s" % a.output)


if __name__ == "__main__":
    main()
