# Release notes

## R1 — 2026-08-02

This is the first revision of the artifact. It responds to the evaluator
inconsistency raised during review and changes **code and documentation only**:
no dataset file, task file, prediction log, or reported number differs from the
release that accompanied the submission.

### One canonical evaluator

`eval/eval_canonical.py` is the single scoring implementation behind the
reported accuracies. Its contract is documented at the top of the file:

- ground truth from `metadata["value"]` at full precision, never the rounded
  `answer` display string
- per-item `metadata["tolerance_pct"]` (B1/B2 ±5%; B3/B4/C3 ±10%)
- prediction parsing that takes the value after the **last** `final answer` /
  `\boxed{}` marker, then the last unit-bearing number, then a bare number — not
  a first-number heuristic
- strict unit matching on the three `numeric_with_unit` tasks, with parse rate
  and unit compliance reported as separate columns

The earlier release also shipped a simplified `eval_main.py`, which the README
described as the main evaluator. That description was incorrect: it takes the
first number in an output and grades against the rounded display string. It
reproduces the multiple-choice columns but not the numeric ones. It has been
replaced by the canonical evaluator, as undertaken in our response.

### Reproduction that runs

```bash
export SHIPBENCH_ROOT=/path/to/dataset
bash examples/reproduce_table3.sh      # Table 3, no API key, about a minute
bash examples/reproduce_paired.sh      # paired frontier statistics
```

Both scripts score the released prediction logs and complete without an API key.
Two portability defects that prevented this are fixed: ground-truth paths are
now resolved from `--task-files` or `$SHIPBENCH_ROOT` rather than a literal
placeholder, and files are opened with an explicit UTF-8 encoding so the scripts
run on machines whose default code page is not UTF-8.

### Documentation

- `docs/pitfalls.md` lists the seven benchmark-design pitfalls once, with
  consistent numbering and a pointer to each appendix section.
- `README.md` is updated throughout to match the contents of this release.

### Scope

Scoring the released prediction logs with `eval/eval_canonical.py` reproduces
Table 3 and the paired frontier statistics reported in the checklist. Files that
belonged to later working versions and were bundled in error are not part of
this release.
