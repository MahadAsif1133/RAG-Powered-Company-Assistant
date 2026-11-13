"""
Build a RAGAS-ready evaluation dataset by running each sample question
through the *real* RAG pipeline (retriever → LLM) and saving the outputs.

Usage:
    cd backend
    python -m evaluation.build_dataset          # uses EVAL_ORG_ID from .env
    python -m evaluation.build_dataset --org-id <uuid>

Output:
    evaluation/results/eval_dataset.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the backend package root is importable when invoked as a script.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Load .env *before* any app imports so settings pick up the keys.
from dotenv import load_dotenv  # noqa: E402
load_dotenv(_BACKEND_DIR / ".env")

from app.services.retriever import retrieve_chunks  # noqa: E402
from app.services.llm import generate_answer        # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------

QUESTIONS_PATH = Path(__file__).resolve().parent / "dataset" / "eval_questions.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Delay between pipeline calls to respect Groq free-tier rate limits (RPM).
INTER_QUERY_DELAY_S = float(os.getenv("EVAL_QUERY_DELAY", "6"))


def build(org_id: str) -> None:
    """Run every question through retrieval + generation and persist results."""
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        questions = json.load(f)

    logger.info("Loaded %d evaluation questions", len(questions))
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    dataset: list[dict] = []

    for idx, entry in enumerate(questions, 1):
        question = entry["question"]
        ground_truth = entry["ground_truth"]

        logger.info("[%d/%d] %s", idx, len(questions), question)

        # --- Step 1: Retrieve ---
        chunks = retrieve_chunks(question, org_id)
        contexts = [c.chunk_text for c in chunks]

        # --- Step 2: Generate ---
        answer, _ = generate_answer(question, chunks)

        dataset.append({
            "user_input": question,
            "response": answer,
            "retrieved_contexts": contexts,
            "reference": ground_truth,
        })

        logger.info("  → %d contexts, answer length=%d", len(contexts), len(answer))

        # Be kind to the free-tier API limits
        if idx < len(questions):
            time.sleep(INTER_QUERY_DELAY_S)

    out_path = RESULTS_DIR / "eval_dataset.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    logger.info("✅ Dataset saved → %s  (%d samples)", out_path, len(dataset))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Build RAGAS eval dataset from the live RAG pipeline")
    parser.add_argument(
        "--org-id",
        default=os.getenv("EVAL_ORG_ID", ""),
        help="Organisation UUID whose documents to query (default: $EVAL_ORG_ID)",
    )
    args = parser.parse_args()

    if not args.org_id:
        parser.error(
            "No org_id supplied. Pass --org-id <uuid> or set EVAL_ORG_ID in backend/.env"
        )

    build(args.org_id)


if __name__ == "__main__":
    main()
