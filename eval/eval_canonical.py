#!/usr/bin/env python3
"""
ShipBench canonical evaluator.

This is the SINGLE scoring implementation behind every accuracy number reported
in the paper (Table 3 zero-shot results, Table 4 v3 ablation, and all appendix
per-ship-type breakdowns). Any other scoring script in this repository is
diagnostic or historical and must not be used to reproduce reported figures.

================================================================================
SCORING CONTRACT
================================================================================

Ground truth
------------
For numeric tasks the target is `metadata["value"]` at FULL precision, never the
rounded `answer` display string. `answer` exists for human readability only:
e.g. B4 item answer = "1.82 m^2" while metadata["value"] = 1.815731836. Grading
against the rounded string silently changes the effective tolerance.

Tolerance
---------
Per-item `metadata["tolerance_pct"]`. Item-level values are authoritative and
already encode the documented per-task defaults (B1/B2 +-5%; B3/B4/C3 +-10%)
together with the small number of item-level overrides. TASK_TOL_FALLBACK below
is used only if an item carries no tolerance field.

Prediction parsing (numeric tasks) -- `parse_value_unit`
--------------------------------------------------------
Applied in this order, first hit wins:

  1. FINAL-ANSWER MARKER. If the output contains "final answer" / "the answer
     is" / "answer:" / "\\boxed{", take the first value+unit pair after the LAST
     such marker. This is what makes the parser safe for chain-of-thought
     outputs, where intermediate arithmetic appears before the answer.
  2. LAST UNIT-BEARING NUMBER anywhere in the text.
  3. FIRST bare number, as a last resort.

A first-number heuristic is NOT used and is not sound here: on a CoT output such
as "The bottom plate is 18 mm thick and 12.5 m wide, so ... Final answer: 1.82
m^2" it returns 18.

Unit handling
-------------
  answer_type == "numeric_with_unit"  (B3 m^3, B4 m^2, C3 mm)
      STRICT. A right magnitude with a wrong or missing unit is scored
      incorrect. `unit_compliance` is reported separately so the two failure
      modes stay distinguishable.
  answer_type == "numeric"            (B1, B2)
      No unit requirement.
  mm^2/mm^3/cm^2/cm^3 are converted to the canonical unit before comparison;
  m^2 / m2 / m-squared spellings are aliased, not converted.

MCQ tasks (A1, A2, C1, C2)
--------------------------
First standalone letter, matched case-insensitively and normalised to upper
case, compared to the key letter. Unparseable output is scored incorrect and
counted in the parse-rate column. On the released predictions this is
equivalent to upper-case-only matching -- no MCQ output in any released log
begins with a lower-case letter -- so the case handling changes no reported
number; it only makes the parser robust for re-runs with other models.

Reporting
---------
Accuracy, 95% bootstrap CI (1,000 resamples, seed 42), parse rate, unit
compliance, median relative error, and per-ship-type breakdown. `--sweep` emits
the tolerance sweep; `--lenient-unit` emits the unit-ignoring diagnostic. Both
are diagnostics: neither is used for a reported accuracy figure.

================================================================================
USAGE
================================================================================

    python eval/eval_canonical.py \
      --predictions <SHIPBENCH_ROOT>/predictions/frontier/gpt-5.5_main_paired.jsonl \
      --task-files  <SHIPBENCH_ROOT>/task_files \
      --output      analysis_repro/gpt55_main.json

    # tolerance sweep (diagnostic)
    python eval/eval_canonical.py --predictions ... --task-files ... --sweep

    # unit-ignoring diagnostic (diagnostic)
    python eval/eval_canonical.py --predictions ... --task-files ... --lenient-unit
"""
from __future__ import annotations

import argparse
import ast
import glob
import json
import os
import random
import re
import statistics
from collections import defaultdict


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

_NUM_UNIT_RE = re.compile(
    r"(-?\d+(?:[\.,]\d+)?(?:\s*[eE][+-]?\d+)?)\s*"
    r"(m\^[23]|m[²³]|m[23]|mm\^[23]|mm[²³]|mm[23]|mm"
    r"|cm\^[23]|cm[²³]|cm[23]|cm|m)?"
)
_FINAL_MARKER_RE = re.compile(
    r"(final\s*answer|the\s*answer\s*is|answer\s*[:=]|\\boxed\{)", re.IGNORECASE
)
_LETTER_RE = re.compile(r"(?:^|[^A-Za-z])([A-Za-z])(?:[^A-Za-z]|$)")

UNIT_ALIASES = {
    "m^3": "m^3", "m³": "m^3", "m3": "m^3",
    "m^2": "m^2", "m²": "m^2", "m2": "m^2",
    "mm^2": "mm^2", "mm²": "mm^2", "mm2": "mm^2",
    "mm^3": "mm^3", "mm³": "mm^3", "mm3": "mm^3",
    "cm^2": "cm^2", "cm²": "cm^2", "cm2": "cm^2",
    "cm^3": "cm^3", "cm³": "cm^3", "cm3": "cm^3",
    "mm": "mm", "cm": "cm", "m": "m",
}

# Only genuine dimensional conversions. Aliases above are spelling, not scale.
UNIT_TO_CANON = {
    ("mm^3", "m^3"): 1e-9, ("cm^3", "m^3"): 1e-6,
    ("mm^2", "m^2"): 1e-6, ("cm^2", "m^2"): 1e-4,
    ("m", "mm"): 1e3, ("cm", "mm"): 10.0,
}

TASK_TOL_FALLBACK = {
    "B1_plate_thickness": 5.0, "B2_stiffener_size": 5.0,
    "B3_cargo_capacity_v1": 10.0, "B4_section_area_v1": 10.0,
    "C3_bulkhead_position": 10.0,
}


def _pair(m):
    if m is None:
        return None, None
    raw_val, raw_unit = m.group(1), (m.group(2) or "").strip().lower()
    try:
        val = float(raw_val.replace(",", "").replace(" ", ""))
    except ValueError:
        return None, None
    return val, (UNIT_ALIASES.get(raw_unit) if raw_unit else None)


def parse_value_unit(text):
    """(value, canonical_unit) under the contract documented at module top."""
    if not isinstance(text, str):
        return None, None
    s = re.sub(r"^(answer|the answer is|approximately|about)[\s:=]*", "",
               text.strip(), flags=re.IGNORECASE)

    markers = list(_FINAL_MARKER_RE.finditer(s))
    if markers:
        m = _NUM_UNIT_RE.search(s[markers[-1].end():])
        if m:
            return _pair(m)

    last = None
    for m in _NUM_UNIT_RE.finditer(s):
        if m.group(2):
            last = m
    if last is not None:
        return _pair(last)

    return _pair(_NUM_UNIT_RE.search(s))


def parse_letter(text):
    if not isinstance(text, str):
        return ""
    m = _LETTER_RE.search(" " + text.strip() + " ")
    if m:
        return m.group(1).upper()
    m = re.match(r"\s*([A-Za-z])", text.strip())
    return m.group(1).upper() if m else ""


# --------------------------------------------------------------------------
# Grading
# --------------------------------------------------------------------------

def grade(pred, item, strict_unit=True, tol_override_pct=None):
    """Grade one prediction.

    Returns a dict with `correct`, `parsed` (a value/letter was recovered),
    `unit_ok` (numeric_with_unit only) and `rel_err` (numeric only).
    """
    out = {"correct": 0, "parsed": 0, "unit_ok": None, "rel_err": None}
    atype = item.get("answer_type", "")
    md = item.get("metadata") or {}

    if atype in ("mcq_letter", "letter"):
        pl, gl = parse_letter(pred), parse_letter(str(item["answer"]))
        out["parsed"] = int(bool(pl))
        out["correct"] = int(pl != "" and pl == gl)
        return out

    if not atype.startswith("numeric"):
        return out

    if "value" not in md:
        return out
    gt_val = float(md["value"])
    gt_unit = md.get("unit")
    tol = float(tol_override_pct if tol_override_pct is not None
                else md.get("tolerance_pct",
                            TASK_TOL_FALLBACK.get(item.get("task"), 5.0))) / 100.0

    val, unit = parse_value_unit(pred)
    if val is None:
        return out
    out["parsed"] = 1

    # A dimensionally equivalent unit is rescaled so that `rel_err` measures the
    # magnitude error rather than the unit choice. It is deliberately NOT
    # promoted to a unit match: `unit_ok` compares the unit the model actually
    # emitted against the one the task asked for, so "1815731 mm^2" for a
    # 1.8157 m^2 target counts as right magnitude, wrong unit. Under the strict
    # (reported) setting that is incorrect; the two failure modes stay separable
    # via the unit-compliance column and --lenient-unit.
    scaled = val
    if unit and gt_unit and unit != gt_unit:
        factor = UNIT_TO_CANON.get((unit, gt_unit))
        if factor is not None:
            scaled = val * factor

    out["rel_err"] = abs(scaled - gt_val) / abs(gt_val) if gt_val else None
    value_ok = out["rel_err"] is not None and out["rel_err"] <= tol

    if atype == "numeric_with_unit":
        out["unit_ok"] = int(unit == gt_unit)
        out["correct"] = int(value_ok and (out["unit_ok"] == 1 or not strict_unit))
    else:
        out["correct"] = int(value_ok)
    return out


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------

# Files that merely enumerate a SUBSET of items for one particular run (the
# frontier paired manifests) or that re-label items for the capability-
# decomposition study. They share qa_ids with the canonical task files, so they
# are loaded at lower priority and can never override a canonical definition.
LOW_PRIORITY_MARKERS = ("_paired", "capability_decomp")


def _gt_priority(path):
    b = os.path.basename(path)
    return (1 if any(m in b for m in LOW_PRIORITY_MARKERS) else 0, b)


def load_ground_truth(task_files_dir, verbose=True):
    """Index the released task files by qa_id under an explicit precedence.

    Canonical task files (`task_main_eval.jsonl` and the per-task
    `task_<ID>_*.jsonl`) are authoritative. Run manifests are loaded afterwards
    and only contribute qa_ids the canonical files do not define.

    The precedence is explicit rather than alphabetical because a manifest can
    carry a per-item field that differs from the canonical definition of the
    same qa_id. Scoring must not depend on which filename happens to sort first,
    so the canonical task files always win and the count of skipped duplicates
    is reported.
    """
    gt, conflicts = {}, 0
    paths = sorted(glob.glob(os.path.join(task_files_dir, "*.jsonl")),
                   key=_gt_priority)
    if not paths:
        raise SystemExit("no *.jsonl found under %s" % task_files_dir)
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                md = d.get("metadata")
                if isinstance(md, str):          # some files store metadata as a repr
                    try:
                        d["metadata"] = ast.literal_eval(md)
                    except Exception:
                        d["metadata"] = {}
                prev = gt.get(d["qa_id"])
                if prev is None:
                    gt[d["qa_id"]] = d
                elif _sig(prev) != _sig(d):
                    conflicts += 1
    if verbose and conflicts:
        print("[gt] %d qa_id(s) redefined by a lower-priority file; canonical "
              "definition kept (see load_ground_truth docstring)" % conflicts)
    return gt


def _sig(d):
    md = d.get("metadata") or {}
    return (d.get("task"), d.get("answer_type"), md.get("value"),
            md.get("unit"), md.get("tolerance_pct"))


def load_predictions(path):
    preds = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                preds.append(json.loads(line))
    return preds


def bootstrap_ci(flags, n_boot=1000, seed=42, conf=0.95):
    n = len(flags)
    if n == 0:
        return 0.0, 0.0
    rng = random.Random(seed)
    means = sorted(sum(flags[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(n_boot))
    lo = means[max(0, int(n_boot * (1 - conf) / 2))]
    hi = means[min(n_boot - 1, int(n_boot * (1 + conf) / 2))]
    return lo, hi


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

SWEEP = [2, 5, 10, 20, 50, 100]


def main():
    ap = argparse.ArgumentParser(description="ShipBench canonical evaluator")
    ap.add_argument("--predictions", required=True)
    ap.add_argument("--task-files", required=True,
                    help="directory holding the released task_*.jsonl files")
    ap.add_argument("--output", default=None)
    ap.add_argument("--sweep", action="store_true",
                    help="diagnostic: accuracy across a tolerance sweep")
    ap.add_argument("--lenient-unit", action="store_true",
                    help="diagnostic: score numeric_with_unit ignoring the unit")
    args = ap.parse_args()

    gt = load_ground_truth(args.task_files)
    preds = load_predictions(args.predictions)

    per_task = defaultdict(lambda: {"correct": [], "parsed": [], "unit": [],
                                    "rel": [], "sweep": [], "ship": defaultdict(list)})
    n_matched = 0
    for p in preds:
        item = gt.get(p.get("qa_id"))
        if item is None:
            continue
        n_matched += 1
        task = item["task"]
        r = grade(p.get("prediction", ""), item, strict_unit=not args.lenient_unit)
        s = per_task[task]
        s["correct"].append(r["correct"])
        s["parsed"].append(r["parsed"])
        if r["unit_ok"] is not None:
            s["unit"].append(r["unit_ok"])
        if r["rel_err"] is not None:
            s["rel"].append(r["rel_err"])
            # Sweep entries carry the unit verdict too, so relaxing the
            # tolerance never silently relaxes the unit requirement as well.
            s["sweep"].append((r["rel_err"], r["unit_ok"]))
        s["ship"][p.get("ship_type") or item.get("ship_type", "?")].append(r["correct"])

    summary = {
        "predictions": os.path.basename(args.predictions),
        "evaluator": "eval_canonical.py",
        "strict_unit": not args.lenient_unit,
        "n_predictions": len(preds),
        "n_matched": n_matched,
        "per_task": {},
    }

    for task in sorted(per_task):
        s = per_task[task]
        n = len(s["correct"])
        lo, hi = bootstrap_ci([float(x) for x in s["correct"]])
        rec = {
            "n": n,
            "accuracy_pct": round(100 * sum(s["correct"]) / n, 2),
            "ci95_pct": [round(100 * lo, 2), round(100 * hi, 2)],
            "parse_rate_pct": round(100 * sum(s["parsed"]) / n, 1),
            "per_ship_pct": {sh: round(100 * sum(v) / len(v), 1)
                             for sh, v in sorted(s["ship"].items())},
        }
        if s["unit"]:
            rec["unit_compliance_pct"] = round(100 * sum(s["unit"]) / len(s["unit"]), 1)
        if s["rel"]:
            rec["median_rel_err_pct"] = round(100 * statistics.median(s["rel"]), 2)
        if args.sweep and s["sweep"]:
            strict = not args.lenient_unit
            rec["tolerance_sweep_pct"] = {
                "+-%d%%" % t: round(100 * sum(
                    1 for err, unit_ok in s["sweep"]
                    if err <= t / 100.0 and (unit_ok != 0 or not strict)) / n, 1)
                for t in SWEEP
            }
        summary["per_task"][task] = rec

    hdr = "%-28s %5s %8s %18s %7s %7s %9s" % (
        "task", "n", "acc%", "95% CI", "parse%", "unit%", "MRE%")
    print("\n=== %s ===" % summary["predictions"])
    print("evaluator: eval_canonical.py   strict_unit=%s   matched %d/%d"
          % (summary["strict_unit"], n_matched, len(preds)))
    print(hdr)
    print("-" * len(hdr))
    for task, r in summary["per_task"].items():
        print("%-28s %5d %8.2f %18s %7.1f %7s %9s" % (
            task, r["n"], r["accuracy_pct"],
            "[%.1f, %.1f]" % tuple(r["ci95_pct"]), r["parse_rate_pct"],
            ("%.1f" % r["unit_compliance_pct"]) if "unit_compliance_pct" in r else "-",
            ("%.2f" % r["median_rel_err_pct"]) if "median_rel_err_pct" in r else "-"))

    if args.sweep:
        print("\ntolerance sweep [diagnostic only -- reported accuracies use "
              "the per-item tolerance above]")
        print("%-28s %s" % ("task", " ".join("%7s" % ("+-%d%%" % t) for t in SWEEP)))
        for task, r in summary["per_task"].items():
            if "tolerance_sweep_pct" in r:
                print("%-28s %s" % (task, " ".join(
                    "%7.1f" % r["tolerance_sweep_pct"]["+-%d%%" % t] for t in SWEEP)))

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print("\nSaved: %s" % args.output)


if __name__ == "__main__":
    main()
