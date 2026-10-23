# Retrieval evaluation

Current Phase 10–12 implementation, setup, verification and limits: [trained intelligence and operational hardening](INTELLIGENCE_HARDENING.md). Earlier milestone sections below describe their original scope.

The evaluation exercises the real authenticated HTTP retrieval/source APIs against an isolated migrated SQLite database. Fixtures are synthetic and explicitly separate from screenshots, real user data and adoption claims. No provider calls or embeddings are used.

## Reproduce

From the repository root, using the backend development environment:

```bash
python backend/evaluation/run.py --ranking legacy
python backend/evaluation/run.py --ranking coverage
python backend/evaluation/connected.py
python backend/evaluation/run.py --output /tmp/parallel-evaluation.json
```

The script creates and removes only a temporary test database. `backend/evaluation/queries.json` contains relevance judgments using fixture aliases. `backend/evaluation/run.py` creates actual decisions, supersession, similar tasks, an archive, contradictory messages, 240 distracting history entries, a distinctive source and a second private workspace. It repeats each query and resolves every returned citation. It also removes a member and checks both removed-member and outsider access. CI runs this command on both supported Python versions.

## Metrics

Results use a maximum page size of five. Precision is relevant returned IDs divided by actual returned IDs (up to five), **not divided by five when fewer results exist**. This is returned-set precision at a five-result cap. Recall divides relevant returned IDs by all judged relevant IDs. For an empty relevance set, a correct empty result scores 1 for precision/recall; unexpected results score 0. If relevant evidence exists but no result is returned, both score 0. Macro values average the eleven query scenarios equally.

Mean reciprocal rank averages `1 / first relevant rank` over the nine queries with nonempty relevance sets; misses contribute 0. Citation correctness checks source existence, same workspace, ID and version for every returned row. Current-state correctness checks that default decision results are proposed/accepted and default task results are unarchived. Unauthorized retrieval count is the number of successful responses in six requests that must return 404, including direct source resolution.

## Observed synthetic-v1 baseline

The 2026-10-23 local run of `deterministic_lexical_v1` produced:

- **11 query scenarios**; macro returned-set precision **0.863636**, recall **0.909091**, MRR **0.888889**.
- **12/12 citations correct**.
- **6/6 current-state checks correct**.
- **0 unauthorized retrievals** across **6 denied requests**.
- Identical ordered results for repeated reads without intervening writes.

The full machine-readable run is stored in [evaluation-baseline.json](evaluation-baseline.json). These are measured values on a small curated fixture, not performance estimates for real projects.

## What the failures mean

The ambiguous query `release UI` returns both release tasks because candidates match any term: precision is 0.5 while recall remains 1. The vocabulary query `sign-out security` misses the relevant authentication decision: precision/recall are 0. The legacy method does not understand synonyms or paraphrases; neither does the new coverage filter. Contradictory conversation assertions are both retrieved as raw messages; the system does not determine which assertion is true.

The regression command requires macro precision at least 0.85, recall at least 0.90, all checked citations/current-state judgments correct, and no unauthorized access. Thresholds preserve this observed baseline; they do not certify semantic understanding. Authorization failures always fail the command. More fixtures should precede threshold changes.

## Limits and next experiments

Both methods are lexical; no semantic-vs-lexical improvement is claimed. Add independently judged paraphrases, negation, domain vocabulary, larger histories, revision-heavy projects, multilingual text, task/decision relevance and more time boundaries. Evaluate retrieval latency and indexing costs on a stated workload before choosing SQLite FTS, PostgreSQL text search or optional versioned embeddings. Any future index must handle correction, archival, membership changes and reproducible rebuilds without exposing other workspaces.

Unit/browser tests complement the benchmark with pagination, temporal boundaries, stale versions, source correction snapshots, private identifiers, session revocation, migration integrity, concurrent workers, approval races and recovery. Test counts are execution evidence, not retrieval quality scores.

## Measured coverage filter and frozen connected queries

The v2 candidate was chosen from the original fixture's ambiguity failure: remove a small explicit stopword set and require `ceil(0.6 × term_count)` title/body coverage. Scores/tie ordering remain explainable SQL. Legacy remains reproducible with `--ranking legacy`; default coverage reports `deterministic_lexical_v2`.

On the original eleven scenarios, v2 measured precision **0.909091** versus **0.863636**, unchanged recall **0.909091** and MRR **0.888889**; **11/11 citations**, **5/5 current-state checks** and **6/6 denials** passed. The ambiguous task query now excludes the partial match; the vocabulary miss remains. See [evaluation-lexical-v2.json](evaluation-lexical-v2.json); the historical v1 result is retained above.

`connected_queries.json` freezes sixteen additional relevance sets before comparing the candidate on connected sources. They were held out from the original eleven-query tuning fixture, but **are author-curated and not independently human-adjudicated**. They cover document phrases/ambiguity/negation excerpts, question stopwords, current and old revisions, imported issues, missing evidence, native tasks and English/Spanish vocabulary gaps. Retrieving a negated source does not prove semantic negation understanding.

Observed connected-fixture results:

- Legacy precision **0.734375**, coverage precision **0.875000**.
- Recall **0.875000** and MRR **0.833333** for both; English paraphrase and Spanish misses remain.
- All **16 legacy / 10 coverage** returned citations resolved to the correct scoped source.
- **6/6** additional source/archive/connection/answer/outsider checks passed; zero unauthorized retrievals.

The local SQLite workload contains 200 unrelated messages, four documents/five revisions, two tasks, two decisions/three revisions and one synthetic imported issue. Ten sequential HTTP requests per query/method produced 160 latency samples each, including TestClient/session/API/SQL overhead: legacy p50 **3.71 ms**, p95 **7.07 ms**; coverage p50 **3.36 ms**, p95 **6.69 ms**. This small single-process sample is not a capacity, concurrency or production-latency claim. Raw measurements and every scenario are in [evaluation-connected.json](evaluation-connected.json).

The connected gate requires no recall/precision regression versus legacy and all lifecycle/access checks passing; both original fixture gates remain. CI uses no model/network calls. Connector fixture tests are distinct from the separately observed live public GitHub read. No model factuality, entailment, independent human judgments, semantic embedding comparison or user-impact improvement was measured.

## Phase 7 holdout: 40 frozen developer-created questions

`python backend/evaluation/pilot.py --output docs/evaluation-pilot.json` creates a disposable migrated SQLite workspace. `pilot_development.json` contains separate smoke prompts; `pilot_holdout.json` freezes 40 relevance sets before the comparison. Labels are **developer-created, not independently human-adjudicated**. Long documents, exact/paraphrased/Spanish queries, multiple sources, superseded choices, conflicting billing excerpts, revoked imports, archived documents, unsupported questions, issue/PR imports and outsider endpoints are included. PDF parsing/page provenance are verified separately by real-parser unit and Chromium journeys; the retrieval fixture documents are Markdown. No paid/network/model calls occur.

At cutoff five, observed legacy / coverage / optional focused results are:

- Macro returned-result precision: **0.618333 / 0.772917 / 0.772917**. Denominator is the number actually returned (up to five); an empty expected/returned set contributes one.
- Strict precision@5: **0.165 / 0.170 / 0.170**. Denominator is always five, including empty result slots; these sparse relevance sets make it much lower than returned precision. Do not conflate the two measures.
- Macro recall@5: **0.850 / 0.900 / 0.900**.
- MRR over queries with nonempty relevance labels: **0.770833 / 0.817708 / 0.838542**.

The focused option adds body phrase weight, a small question-word normalization extension and a current/accepted-record preference. One case, `decision correction`, improves first relevant rank from three to one versus coverage. No MRR case regressed in this run; aggregate precision/recall did not improve. Coverage therefore remains default. Paraphrase and multilingual misses persist; no synonym, semantic-understanding or conflict-resolution claim is supported. Raw per-case gains/misses and source-resolution counts are in [evaluation-pilot.json](evaluation-pilot.json).

Every returned citation was resolved through the same authenticated workspace source API; this checks existence/scope, **not factual entailment**. Seven outsider requests were denied, zero unauthorized retrievals observed, and three unsupported saved-answer questions explicitly abstained. Separate current-state checks assert default superseded decisions, archived passages and revoked imports stay hidden. Regression gates preserve coverage precision/recall versus legacy and focused recall versus coverage, with lifecycle/access failures always fatal. These developer holdout gates are reproducibility checks, not independent quality certification.

The optional character index has lifecycle/provider/failure/fallback tests but no held-out trained-semantic-quality claim. No human usability participants were involved; [pilot browser evidence](PILOT_READINESS.md) reports actual persisted completion and interaction metrics separately from retrieval scores. Original eleven- and sixteen-query baselines remain available and required in CI.

## Phase 10 comparison and verification boundary

[Raw forty-query results](evaluation-phase10.json) preserve the frozen labels. Coverage returned precision/strict P@5/recall/MRR remain **0.772917 / 0.170 / 0.900 / 0.817708**. The character hybrid measured **0.393750 / 0.170 / 0.800 / 0.709375** and therefore remains optional; it is not a trained semantic model. Local mean API latency in this single tiny-corpus run was about **12.09 ms** for coverage and **18.67 ms** for character hybrid. The raw report contains per-case results and maximum timings. These are not independent judgments or production performance measures.

The offline opt-in adds pure trained and trained-hybrid comparisons to the same harness when an operator supplies trusted weights. **Neither ran here.** Trained-provider tests use fabricated vectors, mocked SDK transport or subprocess outputs; they establish boundaries, dimensions, budgets, source invalidation and failure behavior, not semantic relevance. Development prompts, frozen developer holdout, real-model execution and independent human evaluation remain separate evidence categories. No default ranking was changed based on fixture vectors.
