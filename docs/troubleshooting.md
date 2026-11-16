# Troubleshooting Guide

Common setup, runtime, and deployment issues and how to resolve them.

---

## 1. Port Already in Use (`8000` or `3000`)

### Symptoms
- `ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)` (Windows) or `Address already in use` (Linux/macOS).
- Browser shows `ERR_CONNECTION_REFUSED` on `http://localhost:8000` when a process is bound only to IPv4 (`127.0.0.1`) while the browser resolves `localhost` to IPv6 (`::1`).

### Fixes
- **Find and stop the process holding the port (Windows PowerShell):**
  ```powershell
  netstat -ano | Select-String ":8000"
  taskkill /PID <PID> /F
  ```
- **Find and stop the process holding the port (Linux / macOS):**
  ```bash
  lsof -i :8000
  kill -9 <PID>
  ```
- **Or run on a different port:**
  ```bash
  uvicorn main:app --host 0.0.0.0 --port 8001
  ```

---

## 2. Missing `.env` File or Unset API Keys

### Symptoms
- `RuntimeError: GROQ_API_KEY is not set. Add it to backend/.env and restart.`
- `RuntimeError: GROQ_MODEL is not set. Add a model from Groq's current model list (console.groq.com/docs/models) to backend/.env and restart.`
- `RuntimeError: No embedding API key configured. Set HF_TOKEN, VOYAGE_API_KEY, or OPENAI_API_KEY in your .env file.`
- `RuntimeError: MCP_ORG_ID environment variable is required to run the MCP server.`

### Fixes
1. Copy the template file before starting the backend:
   ```bash
   cp backend/.env.example backend/.env
   ```
2. Populate the required keys in `backend/.env`:
   - `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`
   - At least one embedding key: `HF_TOKEN`, `VOYAGE_API_KEY`, or `OPENAI_API_KEY`
   - `GROQ_API_KEY` and an active `GROQ_MODEL` from [Groq's model list](https://console.groq.com/docs/models) (unless using `LLM_PROVIDER=anthropic`)
3. For the Next.js frontend, copy `frontend/.env.example` to `frontend/.env.local` and set `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and `NEXT_PUBLIC_BACKEND_URL`.
4. Note that `REDIS_URL` and `STORAGE_BACKEND=s3` are **optional** — if left empty/default, the backend starts normally without Redis caching or S3 archival.

---

## 3. Slow First Docker Build

### Why It Happens
- `unstructured[pdf,docx]` depends on OCR/layout libraries (`poppler-utils`, `tesseract-ocr`, `opencv`, and PyTorch).
- The first build downloads and compiles these wheels inside the builder stage.

### How It Is Mitigated & What to Check
- `backend/Dockerfile` pre-installs CPU-only PyTorch (`--index-url https://download.pytorch.org/whl/cpu`) so Docker does not download ~2 GB of NVIDIA CUDA packages, and omits `libreoffice` (~500 MB).
- `pyproject.toml` is copied and installed **before** `COPY . .`, so subsequent code edits reuse the cached dependency layer and rebuild in seconds.
- Make sure Docker BuildKit is enabled (`DOCKER_BUILDKIT=1 docker compose build`) and avoid passing `--no-cache` unless `pyproject.toml` or base system packages changed.

---

## 4. Groq Rate Limits (`429 Too Many Requests`) or Retired Model Names (`404 model_not_found`)

### Symptoms
- `POST /api/query` returns HTTP `429`: `"The AI service is receiving too many requests right now. Please wait a minute and try again."`
- `groq.NotFoundError: Error code: 404 - The model ... does not exist or you do not have access to it.`

### Fixes
- **Automatic Retries:** `app/services/llm.py` automatically retries `groq.RateLimitError`, `APIConnectionError`, and `InternalServerError` with exponential backoff (honoring the `Retry-After` response header). You can increase `LLM_MAX_RETRIES` (default `3`) in `backend/.env`.
- **Enable Redis Query Caching:** Set `REDIS_URL=redis://redis:6379/0` (or `redis://localhost:6379/0` locally) so repeated questions within an organization are served from Redis instead of consuming Groq tokens/requests.
- **RAGAS Evaluation Pacing:** When running `python -m evaluation.build_dataset`, set `EVAL_QUERY_DELAY=8` (default `6` seconds) to stay within Groq free-tier requests-per-minute limits.
- **Model Deprecations:** Groq periodically retires older model IDs. Check [https://console.groq.com/docs/models](https://console.groq.com/docs/models) and update `GROQ_MODEL` in `backend/.env`.
