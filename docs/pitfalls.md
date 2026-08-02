# Benchmark-design pitfalls

ShipBench documents **seven** task-design pitfalls found during construction,
together with the corrected task formulation adopted in each case. This file is
the single authoritative list and numbering.

The general lesson: a numerically correct ground-truth label can still produce
uninformative or near-zero accuracy if the *question* carries anchoring,
under-specified semantics, or input-side label leak.

| # | Pitfall | Task affected | Correction adopted | Paper |
|---|---|---|---|---|
| 1 | **Ordinal counting of unlabelled transverse bulkheads.** The `bulkheads_mm` array starts at x=0 (the AP itself), so "the n-th bulkhead from AP" is off-by-one ambiguous depending on convention. LNGC cofferdams additionally place bulkhead pairs ~2.5 m apart that are visually inseparable at compartment-plan render scale. | C1-bulkhead → C3 | Ordinal redefined to exclude the AP; ambiguity documented | App. G.1 |
| 2 | **In-prompt numeric example acts as an anchor.** The format hint "Answer with a single number (e.g., 116000)" caused three of four open-weight models to emit `116000` verbatim across all six ship types. Global accuracy of ~5% looked like a genuine quantitative-reasoning failure and would not have flagged the artifact; only per-ship-type median predictions exposed it. | B3-cargo | Replaced with "Reply with the numeric value only (no units, no commas)" | App. G.2 |
| 3 | **Choice-letter imbalance inherited from the natural class distribution.** With letters assigned in fixed label order and a skewed candidate pool, letter B alone covered 49% of eval items and letter D covered 1.6%. A constant "B" predictor scored 49% on a nominally 4/6-way MCQ. | A3-topology (withdrawn) | Per-item choice shuffling applied to **all** MCQ sub-tasks (A1, A2, C2) | App. G.3 |
| 4 | **Drawing-derivability requires single-hold framing of B3.** Whole-ship cargo capacity embeds a generator-internal bow-taper constant (N−0.3) that is not recoverable from either rendered view. A model with perfect vision and perfect arithmetic would still be off by 0.3/N. | B3-cargo | Reformulated per single hold, excluding the FWD-most hold | App. G.4 |
| 5 | **The distractor pool decides whether an MCQ measures visual reasoning.** With distractors drawn from any named member, the boundary task became 99.8% textbook-determined; a "most frequent option" baseline reached 89.4% against 25% chance. The task measured ship-domain text prior, not the drawing. | C2-boundary | Distractors restricted to members of other compartments of the same ship type; naive baseline falls to 38.9% | App. G.5 |
| 6 | **Numeric-segment-length tasks conflate label OCR with measurement.** An earlier C1 ("C1-seglen") scored 74–76% in aggregate. A per-segment audit split this cleanly: labelled segments (HOLD 1–N, ER) ~100% with prediction–GT Pearson r = +1.0 — the model was reading the on-drawing annotation — while unlabelled end regions (FWD, AFT) collapsed to 1.3% / 0.0%. | C1-seglen | Withdrawn; replaced by the current C1 localisation formulation | App. J |
| 7 | **Input-view label leak.** A1 originally supplied both the section and the compartment-plan view. A shuffled-pair audit localised the entire open-weight signal to the compartment view: swapping the section view left Qwen3-VL at 100% on the kept compartment view's ship type. Open-weight models scored 82.8–100.0% while the frontier reference reached 34.0%. | A1-shiptype | Section-only v2 reformulation, now the canonical A1 task | App. K |

## Numbering

Seven, and only these seven, are the benchmark-design pitfalls this work
documents and corrects. The submitted PDF contains two cross-references that do
not match — a conclusion that reads "nine benchmark-design pitfalls" and one
citation of a "Pitfall 9". Both are residue from a longer manuscript version in
which the numbered series continued past the task-design pitfalls; the series was
cut during condensation but the two references were not updated. They are
corrected in the revision.

The observations those references pointed at are evaluation findings rather than
benchmark-construction defects, and they remain in the paper as such: §5 reports
prompt sensitivity, including the vendor-asymmetric case in which a clarified
prompt that helps one model family induces refusal in another. They are not
listed here because nothing about the benchmark's construction was corrected in
response to them.
