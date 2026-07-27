from __future__ import annotations

import logging
from typing import List, Tuple

from openai import OpenAI  # Groq uses OpenAI-compatible API

from app.core.config import settings
from app.services.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

# Phrase that signals the model chose to punt rather than answer
PUNT_PHRASE = "I don't have information about that"

SYSTEM_PROMPT = """You are an internal company knowledge assistant. Your job is to answer employee questions \
about company policies, HR procedures, SOPs, and onboarding guides.

STRICT RULES:
1. ONLY answer using information from the context sections provided below. Do NOT use any outside knowledge.
2. If the provided context does not contain enough information to answer the question confidently, \
respond EXACTLY with: "I don't have information about that in the uploaded documents — please contact HR/IT directly."
3. Never invent, guess, or extrapolate policy details. Accuracy is critical.
4. When you answer, cite the source document by name at the end of your response in this format:
   Source: [document name]
5. Be concise and professional. Use plain language suitable for all employees.
6. If multiple context sections are relevant, synthesize them into a single clear answer.
"""


def generate_answer(
    question: str,
    chunks: List[RetrievedChunk],
) -> Tuple[str, bool]:
    """
    Build a Groq prompt from retrieved chunks and generate an answer.

    Uses Groq's OpenAI-compatible API endpoint via the openai SDK.
    Model: llama-3.3-70b-versatile (free tier)

    Args:
        question: The employee's question
        chunks:   Retrieved document chunks (empty list = no relevant context found)

    Returns:
        (answer: str, was_confident: bool)
        was_confident is False when the model punted (context insufficient).
    """
    # If no chunks were retrieved at all, short-circuit without calling the LLM
    if not chunks:
        punt_answer = (
            "I don't have information about that in the uploaded documents — "
            "please contact HR/IT directly."
        )
        logger.info("No chunks retrieved — skipping LLM call, returning punt.")
        return punt_answer, False

    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to backend/.env and restart."
        )

    # Build context block from retrieved chunks
    context_sections = []
    for i, chunk in enumerate(chunks, 1):
        context_sections.append(
            f"[Context {i} — Source: {chunk.original_name}]\n{chunk.chunk_text}"
        )
    context_block = "\n\n---\n\n".join(context_sections)

    user_message = f"""Context from company documents:

{context_block}

---

Employee question: {question}

Answer based only on the context above:"""

    logger.info(
        "Calling Groq (%s) with %d context chunks", settings.groq_model, len(chunks)
    )

    # Groq uses an OpenAI-compatible endpoint — just swap the base_url and api_key
    client = OpenAI(
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
    )

    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        max_tokens=1024,
        temperature=0.1,  # Low temp for factual, consistent answers
    )

    answer = response.choices[0].message.content or ""
    answer = answer.strip()
    was_confident = PUNT_PHRASE not in answer

    logger.info(
        "Groq response received — confident=%s, length=%d chars", was_confident, len(answer)
    )
    return answer, was_confident
