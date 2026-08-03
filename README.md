# ShipBench Code (NeurIPS 2026 D&B Track)

Anonymous code release for the ShipBench paper.

**Revision R1 (2026-08-02)** — see [RELEASE_NOTES.md](RELEASE_NOTES.md). R1
changes code and documentation only; no dataset file, task file, prediction log,
or reported number differs from the release that accompanied the submission.

## Reproduce Table 3 in one command, at no cost

```bash
export SHIPBENCH_ROOT=/path/to/dataset       # contains task_files/ and predictions/
bash examples/reproduce_table3.sh
```

This scores the released prediction logs with the canonical evaluator and prints
the full 6 × 9 grid. It needs no API key and takes about a minute. **The released
prediction logs are the reproducible artifact**, so this is the path that
regenerates the published table.

`--rerun-inference` additionally re-queries the two frontier APIs before scoring
(about two hours; the paper reports ~$200 for the full frontier spend). That is
a fresh experiment rather than a reproduction: proprietary endpoints are not
deterministic and the served models change over time, so new predictions will
not match the released logs cell for cell.

## The canonical evaluator

`eval/eval_canonical.py` is the **single** scoring implementation behind every
accuracy figure in the paper. Every other script under `eval/` is diagnostic.
The full scoring contract is documented at the top of the file; in short:

Two invocations of it are used, and which one applies depends on the table.
**Table 3 and the paired frontier statistics use the strict unit rule**, the
default. **The v3 prompt-ablation table uses `--lenient-unit`**, which scores the
numeric value and ignores the unit string — that is what the flag is for. Scoring
the v3 logs under the strict rule instead moves several near-zero cells by
0.5–1.7 pp. The two rules are deliberate, not interchangeable, and the revision
will label them in the table captions.

| | |
|---|---|
| Ground truth | `metadata["value"]`, full precision — never the rounded `answer` display string |
| Tolerance | per-item `metadata["tolerance_pct"]` (B1/B2 ±5%; B3/B4/C3 ±10%) |
| Prediction parsing | value after the **last** `final answer` / `\boxed{}` marker → else the **last** unit-bearing number → else the first bare number |
| Units | strict on `numeric_with_unit` (B3 `m^3`, B4 `m^2`, C3 `mm`); `mm²`/`cm²` etc. converted, spellings aliased |
| MCQ | first standalone capital letter |
| Unparseable | scored incorrect, and counted separately in the parse-rate column |

A first-number heuristic is **not** used. On a chain-of-thought output such as
`"The bottom plate is 18 mm thick ... Final answer: 1.82 m^2"` it would return
`18`.

```bash
python eval/eval_canonical.py \
  --predictions $SHIPBENCH_ROOT/predictions/frontier/gpt-5.5_main_paired.jsonl \
  --task-files  $SHIPBENCH_ROOT/task_files \
  --output      analysis_repro/gpt55_main.json

python eval/eval_canonical.py ... --sweep          # tolerance sweep (diagnostic)
python eval/eval_canonical.py ... --lenient-unit   # ignore units (diagnostic)
```

Reported: accuracy, 95% bootstrap CI (1,000 resamples, seed 42), parse rate,
unit compliance, median relative error, per-ship-type breakdown.

## Structure

```
code/
├── README.md
├── RELEASE_NOTES.md                # what changed in R1 and why
├── requirements.txt
├── docs/
│   └── pitfalls.md                 # the seven benchmark-design pitfalls, once
├── inference/
│   ├── run_frontier_v3.py          # Anthropic Claude Opus 4.7
│   ├── run_frontier_openai.py      # OpenAI gpt-5.5 (concurrent)
│   └── run_vlm_inference.py        # open-weight VLM inference (HF)
├── eval/
│   ├── eval_canonical.py           # THE evaluator — every reported number
│   ├── build_table3.py             # assembles Table 3 from prediction logs
│   ├── paired_frontier_analysis.py # paired bootstrap + McNemar + Clopper-Pearson
│   └── validate_predictions.py     # output-quality diagnostics (does not score)
├── dataset_generation/             # construction pipeline + 6 generators
│   ├── 00_generate_candidates.py … 11_build_task_c.py
│   └── data_generator/             # BULKC / CNTR / LNGC / LPGC / Tanker / VLCC
└── examples/
    ├── reproduce_table3.sh         # Table 3 from the released logs, no API key
    └── reproduce_paired.sh         # paired frontier analysis (cited in §4)
```

## Setup

```bash
pip install -r requirements.txt

export SHIPBENCH_ROOT=/path/to/dataset
export ANTHROPIC_API_KEY=...        # only for --rerun-inference
export OPENAI_API_KEY=...           # only for --rerun-inference
```

## Re-running individual stages

### Frontier inference

```bash
python inference/run_frontier_v3.py \
  --task-file $SHIPBENCH_ROOT/task_files/task_main_eval_opus_paired.jsonl \
  --output predictions_repro/frontier/claude_opus_main.jsonl \
  --n-per-task 200 --max-tokens 1024 --seed 42

python inference/run_frontier_openai.py \
  --task-file $SHIPBENCH_ROOT/task_files/task_main_eval_opus_paired.jsonl \
  --output predictions_repro/frontier/gpt-5.5_main_paired.jsonl \
  --model gpt-5.5 --n-per-task 200 --max-tokens 8192 \
  --reasoning-effort medium --concurrency 16 --seed 42
```

### Open-weight inference (GPU)

```bash
python inference/run_vlm_inference.py \
  --model Qwen/Qwen3-VL-8B-Instruct \
  --output predictions_repro/open_weight/zeroshot/qwen3vl_main.jsonl \
  --split test
```

### Paired frontier statistics

```bash
# one command, from the released logs (this is the script cited in §4)
PRED_DIR=$SHIPBENCH_ROOT/predictions bash examples/reproduce_paired.sh

# or directly
python eval/paired_frontier_analysis.py \
  --opus predictions_repro/frontier/claude_opus_main.jsonl \
  --gpt5 predictions_repro/frontier/gpt-5.5_main_paired.jsonl \
  --output analysis_repro/paired_opus_gpt55.json \
  --name-a Opus --name-b GPT-5.5
```

## Dataset construction

```bash
cd dataset_generation
python 00_generate_candidates.py --seed 42 --output $SHIPBENCH_ROOT/candidates.jsonl
# ... continue with 01_*.py through 11_*.py
```

The six ship-type generators in `data_generator/` are deterministic given
`seed=42`: the same seed yields the same candidate geometry, the same recovered
member polygons, and the same rendered section and compartment-plan PNGs.

The scripts numbered `00`–`11` document how candidates are generated, audited,
stratified, rendered, split, and turned into QA items. They are provided so the
construction procedure is inspectable end to end. They are a working pipeline
rather than a packaged one-command rebuild: task identifiers evolved during
construction — several pitfalls in [docs/pitfalls.md](docs/pitfalls.md) record
tasks that were reformulated or withdrawn — so the QA-building stages do not
map one-to-one onto the final `task_files/` names. **The released
`task_files/` are the authoritative task definitions**, and every reported
number is reproduced from them plus `predictions/` via
`eval/eval_canonical.py`.

## Task files and ground-truth precedence

`task_files/` holds the canonical per-task files plus `task_main_eval.jsonl`.
Files whose names contain `_paired` or `capability_decomp` are **run manifests**:
they enumerate the item subset used for one particular run and share `qa_id`s
with the canonical files. `eval_canonical.py` loads canonical files first and
never lets a manifest override them; it prints a notice if it skips a
conflicting definition. See RELEASE_NOTES.md (d) for the one case where this
matters.

Table 3's A1 column reports the **section-only v2** reformulation of A1
(Pitfall 7, App. K), scored from the `*_a1v2` / `*_a1_section_only` logs. The
`A1_shiptype` task still present inside `*_main.jsonl` is the superseded
two-view v1 and is not what Table 3 prints. `eval/build_table3.py` encodes this
mapping.

## Models / API endpoints

| Vendor | Model | Released | API |
|---|---|---|---|
| Anthropic | `claude-opus-4-7` | 2026-04-14 | `messages.create` |
| OpenAI | `gpt-5.5` | 2026-04-23 | `chat.completions.create` (reasoning_effort=medium, image detail=high) |
| HuggingFace | `Qwen/Qwen3-VL-8B-Instruct@0c351dd` | (pinned) | local, bf16 |
| HuggingFace | `Qwen/Qwen2.5-VL-7B-Instruct@cc59489` | (pinned) | local |
| HuggingFace | `OpenGVLab/InternVL3-8B@853e3a7` | (pinned) | local |
| HuggingFace | `lmms-lab/llava-onevision-qwen2-7b-ov@0d50680` | (pinned) | local |

Two frontier systems are evaluated. Both are run on the same paired task file
with identical prompts and images.

## Statistical methods

- **Paired bootstrap CI** — 1,000 resamples, `seed=42`
- **McNemar test** — exact binomial when `b+c<25`, χ² with continuity correction otherwise
- **Matched-pair OR** — `b/c` paired-aware effect size
- **Clopper–Pearson exact CI** — per-task accuracy, especially sparse-success cells
- **Wilson score CI** — refusal-rate CIs
- **Holm–Bonferroni** — multiple-test correction for the nine-task secondary analyses

## Benchmark-design pitfalls

Seven pitfalls are documented and corrected; see
[docs/pitfalls.md](docs/pitfalls.md) for the single authoritative list and
numbering.

## License

MIT. See LICENSE.
