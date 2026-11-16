# syntax=docker/dockerfile:1

# ── Stage 1: builder ─────────────────────────────────────────
# Dependency files are copied FIRST so this heavy layer is cached
# until pyproject.toml changes (not on every code edit).
FROM python:3.11-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml ./

# Install the dependencies declared in pyproject.toml into an isolated venv.
# (-r pyproject.toml installs the dependency list only, not the project itself.)
# Pre-install CPU-only PyTorch so unstructured[pdf] does not pull ~2GB of CUDA wheels.
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    uv pip install --python /opt/venv/bin/python -r pyproject.toml

# ── Stage 2: runtime ─────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Only what the document parsers need:
#   poppler-utils  - PDF rendering for unstructured/pdf2image
#   tesseract-ocr  - OCR fallback for scanned PDFs (unstructured)
#   libmagic1      - file type detection (unstructured)
#   libglib2.0-0, libgl1 - shared libs required by opencv (pulled in by unstructured[pdf])
# LibreOffice was removed: the parser never invokes it (.docx is read via
# unstructured/python-docx), and it added ~500 MB to the image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
        libmagic1 \
        libglib2.0-0 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd --system --gid 10001 app && \
    useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . .

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

USER app

EXPOSE 8000

# Honors $PORT (Railway sets it); defaults to 8000.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8000'), timeout=5)"

# Shell form of exec so ${PORT} is expanded and uvicorn still receives signals (PID 1).
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
