# Retrieval evaluation

The evaluation exercises the real authenticated HTTP retrieval/source APIs against an isolated migrated SQLite database. Fixtures are synthetic and explicitly separate from screenshots, real user data and adoption claims. No provider calls or embeddings are used.

## Reproduce

From the repository root, using the backend development environment:

```bash
python backend/evaluation/run.py
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

The ambiguous query `release UI` returns both release tasks because candidates match any term: precision is 0.5 while recall remains 1. The vocabulary query `sign-out security` misses the relevant authentication decision: precision/recall are 0. Current lexical scoring does not understand synonyms or paraphrases. Contradictory conversation assertions are both retrieved as raw messages; the system does not determine which assertion is true.

The regression command requires macro precision at least 0.85, recall at least 0.90, all checked citations/current-state judgments correct, and no unauthorized access. Thresholds preserve this observed baseline; they do not certify semantic understanding. Authorization failures always fail the command. More fixtures should precede threshold changes.

## Limits and next experiments

There is one lexical method; no semantic-vs-lexical improvement is claimed. Add independently judged paraphrases, negation, domain vocabulary, larger histories, revision-heavy projects, multilingual text, task/decision relevance and more time boundaries. Evaluate retrieval latency and indexing costs on a stated workload before choosing SQLite FTS, PostgreSQL text search or optional versioned embeddings. Any future index must handle correction, archival, membership changes and reproducible rebuilds without exposing other workspaces.

Unit/browser tests complement the benchmark with pagination, temporal boundaries, stale versions, source correction snapshots, private identifiers, session revocation, migration integrity, concurrent workers, approval races and recovery. Test counts are execution evidence, not retrieval quality scores.
