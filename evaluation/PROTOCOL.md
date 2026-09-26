# Matching evaluation protocol

## Purpose
Measure how well the deterministic matching engine (`POST /api/v1/match`) finds the official
recalls that apply to a described product, and how often it presents wrong matches.

## Dataset (`evaluation/datasets/*.jsonl`)
Built reproducibly from the ingested official data with a fixed seed:
`uv run recallgraph eval build --out ../evaluation/datasets/eval-v1.jsonl --seed 13`.
Every line is one case: `case_id`, `kind`, `query`, `expected` (list of `[source, record id]`),
`label_method`. Labels come from explicit rules over the authoritative records, never from the
matching engine:

| kind | query | expected (label) | completeness |
|---|---|---|---|
| `identifier` | one model/UPC identifier (recalls with <= 10 such records) | every recall with the same normalized identifier | complete by construction |
| `product` | manufacturer + product name with brand words removed + recall year | the source recall | incomplete: other true matches count as FP, so precision is a lower bound |
| `negative_model` | a model number whose prefix does not exist in the data | nothing | complete |
| `negative_manufacturer` | a real product description with a fictitious manufacturer | nothing | complete |

These are **programmatically derived labels ("silver labels")**, not human judgments. They
test retrieval and scoring behavior on real records; they do not capture how real consumers
describe products. Human-labeled cases can be added in the same JSONL format with
`"label_method": "human: <reviewer>, <date>"` and must record why each expected recall applies.

## Metrics (see `backend/src/recallgraph/evaluation/metrics.py`)
Operating points: **strict** (`identifier_match` + `likely`, what the product presents as a
match) and **lenient** (+ `possible`). Pair-level TP/FP/FN, precision, recall, F1,
false-negative rate = FN/(TP+FN); query-level false-positive rate = negative cases with any
positive prediction / negative cases; hit@1 and hit@5 over positive cases.

## Rules
- A dataset file is frozen once results are reported; changes create a new version (`-v2`).
- Evaluation reports record the dataset SHA-256, engine version and full engine configuration.
- Tuning (Step 14) must report before/after on the same frozen dataset.
