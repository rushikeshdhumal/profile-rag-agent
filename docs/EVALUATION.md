# Retrieval evaluation

The retrieval pipeline (`backend/app/retrieval.py`) is measured against a
golden set instead of tuned by feel. This is what makes it safe to change
chunking, fusion weights, the reranker, or the embedding model: run the eval,
see the numbers move, decide.

## What it measures

`evals/run_eval.py`:

1. Builds an isolated agent from `evals/corpus.py` — a deterministic corpus
   that mirrors `examples/sample-profile/` (same resume, LinkedIn/blog/scholar
   text, FAQ) plus a few synthetic GitHub documents. No network call, no
   secret, no live GitHub fetch — this is the only way to get every
   `source_type` category (`resume`, `linkedin`, `faq`, `github`, `identity`)
   covered without depending on a real GitHub account.
2. Runs every case in `evals/dataset.yaml` through the real
   `app.retrieval.retrieve()` pipeline (dense + BM25 + intent-filtered dense,
   RRF fusion, cross-encoder rerank — whatever is actually wired into
   `app.rag`).
3. Computes, per category:
   - `experience` / `logistics` / `github` / `followup`: **recall@5**,
     **recall@10**, **MRR@10** against each case's `expected_sources`.
   - `out_of_scope`: **mean top relevance score** (the reranker's logit for
     the best-ranked chunk). Lower is better here — it means the pipeline
     isn't confidently retrieving anything for a question the profile can't
     answer, which is what lets the grounded system prompt refuse cleanly.
4. Compares against `evals/baseline.json` and exits non-zero on regression
   (recall/MRR dropping more than 5 points, or the out-of-scope score rising
   more than 1.5 logits). CI runs this on every PR.

No LLM call is involved (no `LLM_API_KEY` needed) — only the FastEmbed
embedding model and the cross-encoder reranker run, both CPU ONNX, downloaded
from Hugging Face on first run.

## Running it

```bash
# from the repo root, with backend/requirements-dev.txt installed
python evals/run_eval.py             # compare against the baseline, exit 1 on regression
python evals/run_eval.py --update    # recompute and overwrite the baseline
```

## Extending the golden set

Add cases to `evals/dataset.yaml`:

```yaml
- id: exp-009
  category: experience
  question: "..."
  expected_sources: ["resume.md"]
```

For multi-turn cases (`category: followup`), include a `history` list; the
runner applies the same query-condensation heuristic `app.rag` uses before
retrieving. For `out_of_scope` cases, leave `expected_sources: []`.

After adding real content to `evals/corpus.py` or new questions, re-baseline
with `--update` and commit the new `evals/baseline.json` alongside the
dataset change — a baseline bump should always be reviewed like a code
change, since it's the thing that would otherwise silently mask a regression.

## Reproducibility notes

Two things make ANN vector search slightly non-deterministic run to run:
multi-threaded ONNX Runtime reductions aren't bit-exact, and HNSW is an
*approximate* nearest-neighbor index. Neither matters for real chat traffic,
but both can flip a near-tied rank between two eval runs with zero code
change, which would otherwise make the CI gate flaky. Two mitigations:

- `run_eval.py` sets `EMBEDDING_THREADS=1` (see `app.config.embedding_threads`)
  so the embedding/reranker ONNX sessions run single-threaded.
- Chroma collections are created with a generous `hnsw:search_ef` (200) —
  cheap for the few-hundred-chunk corpora this app actually handles, and
  large enough relative to corpus size that HNSW returns the true top-k
  instead of an approximation.

Even with both, expect roughly one rank of jitter in MRR on categories with
only 7-8 cases (a single flipped rank changes that category's MRR by
~0.06-0.07) — that's why `RECALL_TOLERANCE` in `run_eval.py` is 0.08, not a
tighter number. Recall@k is far more stable than MRR for the same reason:
it only asks whether the right chunk is *in* the top-k, not at which rank.

## Embedding model bake-off (recorded decision)

As part of this upgrade, `all-MiniLM-L6-v2` (the existing default) was
compared against `BAAI/bge-small-en-v1.5` (same 384 dimensions, same class of
footprint) on this golden set. Both scored identically on every metric
(recall@10 = 1.0 across all in-scope categories either way).

That tie isn't strong evidence the two models are equivalent in general — it
mostly reflects that with hybrid fusion (BM25 + intent-filtered dense both
contribute candidates) and a small profile-sized corpus, nearly everything
relevant already lands within the top-30 candidate pool regardless of which
embedding model ranks it, and the cross-encoder reranker then sorts purely
from chunk text, independent of the embedding model. Dense embedding quality
would matter more on a larger corpus or with reranking disabled
(`RERANK_ENABLED=false`).

Given the tie, **`all-MiniLM-L6-v2` stays the default**: switching would force
a breaking reindex of every existing agent (per the standing rule below) for
no measured benefit here. Revisit this if a larger real-world profile corpus
shows a gap the golden set doesn't.

## When retrieval changes require a reindex

Changing chunking (`backend/app/ingest.py`), the embedding model, or anything
that changes what's stored in Chroma metadata invalidates existing agents'
collections. Recreate the agent or call `POST /api/agents/{id}/reindex` with
the owner header. The eval baseline should be re-checked (`--update` if the
change is intentional) in the same change.
