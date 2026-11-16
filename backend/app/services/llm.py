from __future__ import annotations

import logging
import time

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

MAX_TOKENS = 1024
TEMPERATURE = 0.1  # Low temp for factual, consistent answers
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 20.0


# ── Errors ───────────────────────────────────────────────────

class LLMError(RuntimeError):
    """Base class for LLM failures. `str(exc)` is safe to show to the end user."""


class LLMRateLimitError(LLMError):
    """The provider kept rate limiting us after all retries."""


class LLMUnavailableError(LLMError):
    """The provider could not be reached or kept failing after all retries."""


# ── Public API (signature unchanged) ─────────────────────────

def generate_answer(
    question: str,
    chunks: list[RetrievedChunk],
) -> tuple[str, bool]:
    """
    Build a prompt from retrieved chunks and generate an answer with the
    configured LLM provider (LLM_PROVIDER: "groq" default, or "anthropic").

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

    provider = (settings.llm_provider or "groq").strip().lower()
    if provider == "groq":
        call = _call_groq
    elif provider == "anthropic":
        call = _call_anthropic
    else:
        raise RuntimeError(f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Use 'groq' or 'anthropic'.")

    logger.info("Calling LLM provider=%s with %d context chunks", provider, len(chunks))
    answer = _with_retries(lambda: call(SYSTEM_PROMPT, user_message), provider).strip()
    was_confident = PUNT_PHRASE not in answer

    logger.info("LLM response received — confident=%s, length=%d chars", was_confident, len(answer))
    return answer, was_confident


# ── Retry / backoff ──────────────────────────────────────────

def _retry_after_seconds(exc: Exception) -> float | None:
    """Read a Retry-After header from an SDK error response, if present."""
    try:
        value = exc.response.headers.get("retry-after")  # type: ignore[attr-defined]
        return float(value) if value else None
    except Exception:
        return None


def _with_retries(fn, provider: str):
    """
    Run `fn`, retrying rate-limit and transient errors with exponential backoff.
    Raises LLMRateLimitError / LLMUnavailableError with a user-safe message when exhausted.
    """
    retryable, rate_limit_types = _error_types(provider)
    attempts = max(0, settings.llm_max_retries) + 1
    last_exc: Exception | None = None

    for attempt in range(attempts):
        try:
            return fn()
        except retryable as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt == attempts - 1:
                break
            delay = _retry_after_seconds(exc)
            if delay is None:
                delay = BACKOFF_BASE_SECONDS * (2**attempt)
            delay = min(delay, BACKOFF_MAX_SECONDS)
            logger.warning(
                "%s call failed (%s); retry %d/%d in %.1fs",
                provider, type(exc).__name__, attempt + 1, attempts - 1, delay,
            )
            time.sleep(delay)

    if isinstance(last_exc, rate_limit_types):
        raise LLMRateLimitError(
            "The AI service is receiving too many requests right now. "
            "Please wait a minute and try again."
        ) from last_exc
    raise LLMUnavailableError(
        "The AI service is temporarily unavailable. Please try again shortly."
    ) from last_exc


def _error_types(provider: str) -> tuple[tuple[type[Exception], ...], tuple[type[Exception], ...]]:
    """(retryable exception types, subset that means 'rate limited') for the provider SDK."""
    if provider == "groq":
        import groq

        rate = (groq.RateLimitError,)
        return rate + (groq.APIConnectionError, groq.InternalServerError), rate
    import anthropic

    rate = (anthropic.RateLimitError,)
    return rate + (anthropic.APIConnectionError, anthropic.InternalServerError), rate


# ── Providers ────────────────────────────────────────────────

def _call_groq(system_prompt: str, user_message: str) -> str:
    """Groq chat completion via the official `groq` SDK (OpenAI-style chat messages)."""
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not set. Add it to backend/.env and restart.")
    if not settings.groq_model:
        raise RuntimeError(
            "GROQ_MODEL is not set. Add a model from Groq's current model list "
            "(console.groq.com/docs/models) to backend/.env and restart."
        )
    from groq import Groq

    # max_retries=0: retries are handled by _with_retries so backoff is consistent.
    client = Groq(api_key=settings.groq_api_key, max_retries=0)
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
    )
    return response.choices[0].message.content or ""


def _call_anthropic(system_prompt: str, user_message: str) -> str:
    """Optional Anthropic path (LLM_PROVIDER=anthropic). Kept so nothing is deleted."""
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to backend/.env and restart.")
    if not settings.anthropic_model:
        raise RuntimeError("ANTHROPIC_MODEL is not set. Add it to backend/.env and restart.")
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=0)
    response = client.messages.create(
        model=settings.anthropic_model,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
    )
    return "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
