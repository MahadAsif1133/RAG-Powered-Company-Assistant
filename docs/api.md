# API Endpoint Reference

All `/api/*` endpoints require a valid Supabase Auth Bearer JWT in the `Authorization` header:

```http
Authorization: Bearer <supabase-access-token>
```

The backend resolves `user_id`, `org_id`, and `role` (`admin` or `employee`) from the `users` table and scopes every operation strictly to `org_id`.

---

## 1. Upload Document

- **Method & Path:** `POST /api/documents/upload`
- **Auth:** Admin JWT (`role == "admin"`)
- **Content-Type:** `multipart/form-data`
- **Supported Extensions:** `.pdf`, `.docx`, `.doc`, `.txt` (max `50 MB`)

### Example Request

```bash
curl -X POST "http://localhost:8000/api/documents/upload" \
  -H "Authorization: Bearer <admin-jwt>" \
  -F "file=@HR_Policy_Handbook.pdf"
```

### Example Response (`202 Accepted`)

```json
{
  "document_id": "22222222-2222-2222-2222-222222222222",
  "message": "Document uploaded. Ingestion started — poll /status for progress."
}
```

### Error Responses
- `400 Bad Request` — Unsupported file extension or empty file.
- `401 Unauthorized` / `403 Forbidden` — Missing/invalid JWT or non-admin user.
- `413 Request Entity Too Large` — File exceeds 50 MB limit.

---

## 2. List Documents

- **Method & Path:** `GET /api/documents`
- **Auth:** Admin JWT (`role == "admin"`)
- **Description:** Returns all documents belonging to the caller's organization, ordered by `uploaded_at` descending.

### Example Request

```bash
curl -X GET "http://localhost:8000/api/documents" \
  -H "Authorization: Bearer <admin-jwt>"
```

### Example Response (`200 OK`)

```json
[
  {
    "id": "22222222-2222-2222-2222-222222222222",
    "filename": "9f8c1d2e3a4b5c6d7e8f9a0b1c2d3e4f_HR_Policy_Handbook.pdf",
    "original_name": "HR_Policy_Handbook.pdf",
    "file_type": "pdf",
    "file_size": 184320,
    "status": "ready",
    "chunk_count": 12,
    "error_msg": null,
    "uploaded_at": "2026-11-16T12:00:00.000000+00:00",
    "updated_at": "2026-11-16T12:00:08.000000+00:00"
  }
]
```

---

## 3. Get Document Ingestion Status

- **Method & Path:** `GET /api/documents/{document_id}/status`
- **Auth:** Admin JWT (`role == "admin"`)
- **Description:** Poll the background ingestion status (`processing`, `ready`, or `failed`) for a single document in the caller's organization.

### Example Request

```bash
curl -X GET "http://localhost:8000/api/documents/22222222-2222-2222-2222-222222222222/status" \
  -H "Authorization: Bearer <admin-jwt>"
```

### Example Response (`200 OK`)

```json
{
  "id": "22222222-2222-2222-2222-222222222222",
  "status": "ready",
  "chunk_count": 12,
  "error_msg": null,
  "updated_at": "2026-11-16T12:00:08.000000+00:00"
}
```

### Error Responses
- `404 Not Found` — Document does not exist or belongs to another organization.

---

## 4. Delete Document

- **Method & Path:** `DELETE /api/documents/{document_id}`
- **Auth:** Admin JWT (`role == "admin"`)
- **Description:** Deletes the document row and cascades deletion to all associated `document_chunks`. If `STORAGE_BACKEND=s3`, also deletes `organizations/{org_id}/{filename}` from S3, and invalidates the organization's Redis query cache.

### Example Request

```bash
curl -X DELETE "http://localhost:8000/api/documents/22222222-2222-2222-2222-222222222222" \
  -H "Authorization: Bearer <admin-jwt>"
```

### Example Response (`204 No Content`)

Empty response body (`204 No Content`).

### Error Responses
- `404 Not Found` — Document does not exist or belongs to another organization.

---

## 5. Query Knowledge Base (RAG)

- **Method & Path:** `POST /api/query`
- **Auth:** User JWT (`admin` or `employee`)
- **Rate Limit:** `QUERY_RATE_LIMIT` (default `10/minute` per IP via `slowapi`, plus per-organization fixed-window rate limiting when `REDIS_URL` is configured).

### Example Request

```bash
curl -X POST "http://localhost:8000/api/query" \
  -H "Authorization: Bearer <user-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How many days of paid annual leave do full-time employees receive?"
  }'
```

### Example Response — Confident Answer (`200 OK`)

```json
{
  "answer": "Full-time employees receive 25 days of paid annual leave per year.\n\nSource: [HR_Policy_Handbook.pdf]",
  "sources": [
    {
      "original_name": "HR_Policy_Handbook.pdf",
      "filename": "9f8c1d2e3a4b5c6d7e8f9a0b1c2d3e4f_HR_Policy_Handbook.pdf",
      "document_id": "22222222-2222-2222-2222-222222222222"
    }
  ],
  "was_answered_confidently": true,
  "latency_ms": 640
}
```

### Example Response — Punted / Insufficient Context (`200 OK`)

```json
{
  "answer": "I don't have information about that in the uploaded documents — please contact HR/IT directly.",
  "sources": [],
  "was_answered_confidently": false,
  "latency_ms": 115
}
```

### Error Responses
- `400 Bad Request` — Empty question or question exceeds 2000 characters.
- `429 Too Many Requests` — Rate limit exceeded (per-IP, per-organization Redis limiter, or upstream LLM rate limit after retries).
- `503 Service Unavailable` — Upstream LLM service remained unavailable after retries.
