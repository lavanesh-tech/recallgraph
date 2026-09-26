# Experiment: semantic retrieval for matching (Step 19)

Pre-registered on 2026-09-26, BEFORE any results were produced.

## Question
Does embedding-based retrieval (pgvector, HNSW, cosine) improve product-to-recall matching
over the deterministic engine `match-2`?

## Setup
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2` (384 dims, local ONNX via fastembed),
  text = recall title + product names/types; query text = manufacturer + description + category.
- Dataset: `evaluation/datasets/eval-v1.jsonl`, **test split** (held out, also used in Step 14).
- Variants: `baseline` (match-2) · `semantic-candidates` (+100 nearest recalls as candidates) ·
  `semantic-signal` (candidates + similarity signal, weight 0.15).

## Decision rule (fixed in advance)
Adopt a semantic variant only if, on the test split, ALL hold versus baseline:
1. strict overall F1 improves by >= 0.02,
2. strict overall hit@1 does not decrease,
3. mean matching latency is at most 2x the baseline.
Otherwise semantic retrieval is **not adopted**; the result is still recorded as evidence.

## Known limitation
eval-v1 product queries are derived from recall product names, which favors lexical matching;
a null result here does not prove embeddings are useless for real consumer phrasing.
