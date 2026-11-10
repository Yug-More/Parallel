# Retrieval evaluation freeze

9 November 2026. Ranking code and relevance labels were unchanged in this cycle. All fixtures are synthetic and developer-created; none establishes independent relevance, production latency or trained-model quality.

Reproduce from the root with backend development dependencies:

```bash
python backend/evaluation/run.py --ranking legacy
python backend/evaluation/run.py --ranking coverage
python backend/evaluation/connected.py
python backend/evaluation/pilot.py
```

[Original evaluation methodology](EVALUATION.md) explains source selection, abstention, ranking and known failures. Current full outputs are [legacy](final-evaluation/legacy.json), [coverage](final-evaluation/coverage.json), [connected](final-evaluation/connected.json) and [holdout](final-evaluation/pilot.json). Do not mix metrics across these datasets.

The original 11-query fixture gives coverage recall@5 0.909091 and MRR 0.888889; the 16-query connected fixture gives coverage recall@5 0.875 and MRR 0.833333. The frozen 40-query holdout gives default coverage recall@5 **0.900**, MRR **0.817708**, precision over returned results **0.772917**, and strict precision@5 **0.170**. Strict precision divides by five, including empty slots. The earlier 90%/0.818 claim is reproducible specifically on this holdout, not a general performance estimate.

On the same 40 cases: legacy recall 0.850/MRR 0.770833; optional focused recall 0.900/MRR 0.838542; optional character hybrid recall 0.800/MRR 0.725. Coverage remains the default. Character ngrams are not trained semantics. The trained adapter was not run.

Connected coverage latency was p50 4.446ms/p95 8.649ms for 160 sequential SQLite API/session requests: 200 unrelated messages, four documents/five revisions, two tasks, two decisions/three revisions and one synthetic imported issue. Holdout coverage mean was 11.536ms, maximum 60.143ms in this run. These are different workloads, lack concurrent production load and are sensitive to local scheduling; no improvement claim is made. The holdout separately recorded seven authorization denials and zero unauthorized leaks within tested cases.

Vocabulary/paraphrase and Spanish queries still miss relevant evidence; ambiguous terms can retrieve irrelevant records. Source identity/citation resolution does not establish entailment or truth. Author-curated judgments and known fixture contents can bias evaluation. Independent judgments, multilingual coverage, real trained-model evaluation and representative user/load studies remain follow-up work.
