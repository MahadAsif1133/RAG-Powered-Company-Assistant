const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

async function fetchWithAuth(path: string, token: string, options: RequestInit = {}) {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }

  return res.json();
}

// ── Documents ────────────────────────────────────────────────

export async function uploadDocument(file: File, token: string) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${BACKEND_URL}/api/documents/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }

  return res.json();
}

export async function listDocuments(token: string) {
  return fetchWithAuth("/api/documents", token);
}

export async function getDocumentStatus(documentId: string, token: string) {
  return fetchWithAuth(`/api/documents/${documentId}/status`, token);
}

export async function deleteDocument(documentId: string, token: string) {
  const res = await fetch(`${BACKEND_URL}/api/documents/${documentId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok && res.status !== 204) {
    throw new Error(`Delete failed: ${res.status}`);
  }
}

// ── Query ────────────────────────────────────────────────────

export async function queryDocuments(question: string, token: string) {
  return fetchWithAuth("/api/query", token, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

// ── Analytics ────────────────────────────────────────────────

export async function getAnalyticsSummary(token: string) {
  return fetchWithAuth("/api/query/analytics/summary", token);
}
