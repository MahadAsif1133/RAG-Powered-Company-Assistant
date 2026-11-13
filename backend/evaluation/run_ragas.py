"""
Run RAGAS evaluation metrics on a previously-built dataset.

Usage:
    cd backend
    python -m evaluation.run_ragas                        # default paths
    python -m evaluation.run_ragas --dataset path/to/eval_dataset.json

Metrics evaluated:
    • Faithfulness        – is the answer grounded in retrieved contexts?
    • ResponseRelevancy   – does the answer address the question?
    • LLMContextPrecisionWithReference – are the relevant chunks ranked highest?
    • LLMContextRecall    – did the retriever fetch all needed information?

Judge LLM:  Groq (via langchain-groq, model from GROQ_MODEL env var)
Embeddings: Voyage AI (via langchain-voyageai, voyage-3-large)

Output:
    evaluation/results/ragas_scores.json   – per-sample + aggregate scores
    evaluation/results/ragas_scores.csv    – same data in CSV for quick inspection
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the backend package root is importable.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — these pull in heavy deps from the [eval] optional group.
# ---------------------------------------------------------------------------


def _build_evaluator_llm():
    """Wrap Groq as a RAGAS-compatible LLM via langchain-groq."""
    from langchain_groq import ChatGroq  # type: ignore
    from ragas.llms import LangchainLLMWrapper  # type: ignore

    groq_api_key = os.environ.get("GROQ_API_KEY", "")
    groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    if not groq_api_key:
        raise RuntimeError("GROQ_API_KEY is required for RAGAS evaluation")

    llm = ChatGroq(
        model=groq_model,
        api_key=groq_api_key,
        temperature=0,
        # Groq does not support n>1 completions — keep n=1 (default).
    )
    return LangchainLLMWrapper(llm)


def _build_evaluator_embeddings():
    """Wrap Voyage AI as RAGAS-compatible embeddings via langchain-voyageai."""
    from langchain_voyageai import VoyageAIEmbeddings  # type: ignore
    from ragas.embeddings import LangchainEmbeddingsWrapper  # type: ignore

    voyage_api_key = os.environ.get("VOYAGE_API_KEY", "")
    if not voyage_api_key:
        raise RuntimeError("VOYAGE_API_KEY is required for RAGAS evaluation")

    embeddings = VoyageAIEmbeddings(
        model="voyage-3-large",
        voyage_api_key=voyage_api_key,
    )
    return LangchainEmbeddingsWrapper(embeddings)


def run(dataset_path: Path) -> None:
    """Load the dataset, run RAGAS metrics, and save results."""
    from ragas import EvaluationDataset, SingleTurnSample, evaluate  # type: ignore
    from ragas.metrics import (  # type: ignore
        Faithfulness,
        ResponseRelevancy,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
    )
    from ragas.run_config import RunConfig  # type: ignore

    # ------------------------------------------------------------------
    # 1. Load dataset built by build_dataset.py
    # ------------------------------------------------------------------
    with open(dataset_path, encoding="utf-8") as f:
        raw = json.load(f)

    logger.info("Loaded %d samples from %s", len(raw), dataset_path)

    samples = [
        SingleTurnSample(
            user_input=entry["user_input"],
            response=entry["response"],
            retrieved_contexts=entry["retrieved_contexts"],
            reference=entry["reference"],
        )
        for entry in raw
    ]
    eval_dataset = EvaluationDataset(samples=samples)

    # ------------------------------------------------------------------
    # 2. Build evaluator LLM + embeddings
    # ------------------------------------------------------------------
    evaluator_llm = _build_evaluator_llm()
    evaluator_embeddings = _build_evaluator_embeddings()

    # ------------------------------------------------------------------
    # 3. Configure metrics
    # ------------------------------------------------------------------
    metrics = [
        Faithfulness(llm=evaluator_llm),
        ResponseRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings),
        LLMContextPrecisionWithReference(llm=evaluator_llm),
        LLMContextRecall(llm=evaluator_llm),
    ]

    # ------------------------------------------------------------------
    # 4. RunConfig — tuned for Groq free-tier rate limits
    #    • Low max_workers to avoid 429s
    #    • Generous retries + timeout
    # ------------------------------------------------------------------
    run_config = RunConfig(
        max_workers=2,
        max_wait=90,
        max_retries=10,
        timeout=120,
    )

    # ------------------------------------------------------------------
    # 5. Evaluate
    # ------------------------------------------------------------------
    logger.info("Starting RAGAS evaluation (this may take several minutes)…")

    result = evaluate(
        dataset=eval_dataset,
        metrics=metrics,
        run_config=run_config,
        raise_exceptions=False,
    )

    # ------------------------------------------------------------------
    # 6. Save results
    # ------------------------------------------------------------------
    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    # Per-sample DataFrame
    df = result.to_pandas()

    csv_path = results_dir / "ragas_scores.csv"
    df.to_csv(csv_path, index=False)
    logger.info("Per-sample CSV → %s", csv_path)

    # Aggregate + per-sample JSON
    aggregate = {k: float(v) for k, v in result.scores.items()} if hasattr(result, "scores") else {}
    output = {
        "aggregate_scores": aggregate,
        "per_sample": json.loads(df.to_json(orient="records", force_ascii=False)),
    }
    json_path = results_dir / "ragas_scores.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logger.info("Full JSON   → %s", json_path)

    # Pretty-print aggregate
    logger.info("─── Aggregate Scores ───")
    for metric_name, score in aggregate.items():
        logger.info("  %s: %.4f", metric_name, score)
    logger.info("────────────────────────")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    default_dataset = Path(__file__).resolve().parent / "results" / "eval_dataset.json"

    parser = argparse.ArgumentParser(description="Run RAGAS evaluation metrics")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=default_dataset,
        help="Path to the eval_dataset.json produced by build_dataset.py",
    )
    args = parser.parse_args()

    if not args.dataset.exists():
        parser.error(
            f"Dataset not found at {args.dataset}.\n"
            "Run  python -m evaluation.build_dataset  first."
        )

    run(args.dataset)


if __name__ == "__main__":
    main()
