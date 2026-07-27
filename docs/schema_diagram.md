# Database Schema Diagram

Entity-relationship diagram for the Company Knowledge Assistant multi-tenant RAG system.

```mermaid
erDiagram
    organizations {
        uuid id PK
        text name
        text slug "unique URL slug"
        timestamptz created_at
    }

    users {
        uuid id PK "= auth.users.id"
        uuid org_id FK
        user_role role "admin | employee"
        text full_name
        text email
        timestamptz created_at
    }

    documents {
        uuid id PK
        uuid org_id FK
        text filename "storage key"
        text original_name "user-visible"
        text file_type "pdf | docx | txt"
        bigint file_size
        uuid uploaded_by FK
        document_status status "processing | ready | failed"
        int chunk_count
        text error_msg
        timestamptz uploaded_at
        timestamptz updated_at
    }

    document_chunks {
        uuid id PK
        uuid document_id FK
        uuid org_id FK "denormalized for perf"
        int chunk_index
        text chunk_text
        vector_1024 embedding "HNSW cosine index"
        int token_count
        timestamptz created_at
    }

    query_logs {
        uuid id PK
        uuid org_id FK
        uuid user_id FK
        text question
        uuid_array retrieved_chunk_ids
        text answer
        boolean was_answered_confidently
        int latency_ms
        timestamptz created_at
    }

    slack_workspaces {
        uuid id PK
        uuid org_id FK
        text slack_team_id "unique"
        text slack_team_name
        timestamptz installed_at
    }

    slack_users {
        uuid id PK
        uuid user_id FK
        uuid org_id FK
        text slack_user_id
        text slack_team_id
        timestamptz created_at
    }

    organizations ||--o{ users : "has"
    organizations ||--o{ documents : "owns"
    organizations ||--o{ document_chunks : "owns"
    organizations ||--o{ query_logs : "generates"
    organizations ||--o{ slack_workspaces : "linked to"
    organizations ||--o{ slack_users : "has"

    users ||--o{ documents : "uploads"
    users ||--o{ query_logs : "asks"
    users ||--o| slack_users : "maps to"

    documents ||--o{ document_chunks : "chunked into"
    document_chunks }o--o{ query_logs : "retrieved in"

    slack_workspaces ||--o{ slack_users : "contains"
```

## Key Design Decisions

| Decision | Reason |
|----------|--------|
| `org_id` denormalized on `document_chunks` | Avoids a JOIN on every vector search — cosine similarity scan + org filter happens in one index pass |
| HNSW index (not IVFFlat) | No training/`VACUUM` step; better recall at small-to-medium scale (<1M chunks); online updates |
| `vector(1024)` | Voyage AI `voyage-3-large` dimensions; change to `vector(1536)` for OpenAI `text-embedding-3-small` |
| `users.id` = `auth.users.id` | Direct JWT → user resolution without extra lookup; Supabase Auth manages the auth side |
| RLS on all tables | Service-role key (backend) bypasses for writes; protects against accidental anon API exposure |
| `similarity_threshold = 0.3` in function | Filters out low-relevance chunks before returning; prevents garbage context in LLM prompt |
