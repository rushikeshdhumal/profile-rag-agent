"""Retrieval evaluation runner.

Builds an isolated, offline eval agent from evals/corpus.py, runs every case
in evals/dataset.yaml through the real retrieval pipeline (app.retrieval),
and compares recall/MRR (and, for out-of-scope cases, top relevance score)
against evals/baseline.json. No LLM call, no API key, no network secrets --
only the FastEmbed/cross-encoder ONNX models are downloaded on first run.

Usage:
    python evals/run_eval.py             # compare against baseline, exit 1 on regression
    python evals/run_eval.py --update    # recompute and overwrite the baseline
"""

from __future__ import annotations

import argparse
import contextlib
import gc
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT / "backend", REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

DATASET_PATH = Path(__file__).resolve().parent / "dataset.yaml"
BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"

RECALL_TOLERANCE = 0.08  # fractional. With only 7-8 cases per category, a single rank
# flipping by one position on a near-tied ANN result changes a category's MRR by ~0.06-0.07
# even with zero code change (HNSW is approximate); this must be wider than that jitter.
OOS_SCORE_TOLERANCE = 1.5  # rerank logits aren't 0..1 scaled; use an absolute band
IN_SCOPE_CATEGORIES = ("experience", "logistics", "github", "followup")
EVAL_AGENT_ID = "eval-agent"


def _setup_eval_agent(data_dir: Path) -> str:
    os.environ["DATA_DIR"] = str(data_dir)
    # Single-threaded ONNX Runtime avoids run-to-run floating-point jitter in
    # multi-threaded reductions, which can otherwise flip near-tied ANN ranks
    # on a small corpus and make the baseline comparison flaky.
    os.environ["EMBEDDING_THREADS"] = "1"

    from app.config import get_settings

    get_settings.cache_clear()
    get_settings()

    from evals.corpus import (
        build_eval_agent,
        build_eval_corpus,  # noqa: F401  (import-time sanity check)
    )

    build_eval_agent(EVAL_AGENT_ID)
    return EVAL_AGENT_ID


def _teardown_eval_agent() -> None:
    from app.bm25 import invalidate_all_bm25_indexes
    from app.vectorstore import close_all_clients

    close_all_clients()
    invalidate_all_bm25_indexes()
    gc.collect()


def _load_dataset() -> list[dict[str, Any]]:
    return yaml.safe_load(DATASET_PATH.read_text(encoding="utf-8"))


def _run_case(agent_id: str, case: dict[str, Any]) -> dict[str, Any]:
    from app.rag import _condense_query, _looks_context_dependent
    from app.retrieval import retrieve
    from app.schemas import ChatMessage

    history = [ChatMessage(**h) for h in case.get("history", [])]
    query = case["question"]
    if history and _looks_context_dependent(query, history):
        with contextlib.suppress(Exception):
            query = _condense_query(query, history)

    chunks = retrieve(agent_id, query, k=10, candidate_k=30)
    sources = [c.get("source") for c in chunks]
    top_score = 0.0
    if chunks:
        top_score = chunks[0].get("rerank_score", chunks[0].get("fusion_score", 0.0))
    return {"sources": sources, "top_score": top_score}


def _recall_at(sources: list[str], expected: list[str], k: int) -> float:
    if not expected:
        return 1.0
    return 1.0 if any(s in sources[:k] for s in expected) else 0.0


def _mrr_at(sources: list[str], expected: list[str], k: int) -> float:
    for rank, source in enumerate(sources[:k], start=1):
        if source in expected:
            return 1.0 / rank
    return 0.0


def _compute_metrics(by_category: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for category, cases in by_category.items():
        if category == "out_of_scope":
            scores = [c["top_score"] for c in cases]
            metrics[category] = {
                "mean_top_score": sum(scores) / len(scores) if scores else 0.0,
                "n": len(cases),
            }
        else:
            r5 = [_recall_at(c["sources"], c["expected_sources"], 5) for c in cases]
            r10 = [_recall_at(c["sources"], c["expected_sources"], 10) for c in cases]
            mrr = [_mrr_at(c["sources"], c["expected_sources"], 10) for c in cases]
            metrics[category] = {
                "recall_at_5": sum(r5) / len(r5),
                "recall_at_10": sum(r10) / len(r10),
                "mrr_at_10": sum(mrr) / len(mrr),
                "n": len(cases),
            }

    in_scope_recall5 = [metrics[c]["recall_at_5"] for c in IN_SCOPE_CATEGORIES if c in metrics]
    metrics["overall"] = {
        "recall_at_5": sum(in_scope_recall5) / len(in_scope_recall5) if in_scope_recall5 else 0.0,
    }
    return metrics


def _check_regression(metrics: dict[str, Any], baseline: dict[str, Any]) -> bool:
    regressed = False
    for category, values in metrics.items():
        base_values = baseline.get(category, {})
        for metric_name, value in values.items():
            if metric_name == "n":
                continue
            base_value = base_values.get(metric_name)
            if base_value is None:
                continue
            if metric_name == "mean_top_score":
                if value > base_value + OOS_SCORE_TOLERANCE:
                    print(f"REGRESSION {category}.{metric_name}: {value:.3f} > baseline {base_value:.3f}")
                    regressed = True
            elif value < base_value - RECALL_TOLERANCE:
                print(f"REGRESSION {category}.{metric_name}: {value:.3f} < baseline {base_value:.3f}")
                regressed = True
    return regressed


def run(update: bool) -> int:
    dataset = _load_dataset()

    # ignore_cleanup_errors: chromadb's hnswlib index can keep an mmap open
    # briefly after we drop our client references; don't fail the run over it.
    with tempfile.TemporaryDirectory(prefix="rag-eval-", ignore_cleanup_errors=True) as tmp:
        agent_id = _setup_eval_agent(Path(tmp))

        by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for case in dataset:
            result = _run_case(agent_id, case)
            by_category[case["category"]].append({**case, **result})

        _teardown_eval_agent()

    metrics = _compute_metrics(by_category)
    print(json.dumps(metrics, indent=2))

    if update or not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        print(f"Baseline written to {BASELINE_PATH}")
        return 0

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if _check_regression(metrics, baseline):
        print("Retrieval eval FAILED (regression detected).")
        return 1
    print("Retrieval eval PASSED.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the retrieval golden-set eval.")
    parser.add_argument("--update", action="store_true", help="Recompute and overwrite the baseline.")
    args = parser.parse_args()
    sys.exit(run(update=args.update))


if __name__ == "__main__":
    main()
