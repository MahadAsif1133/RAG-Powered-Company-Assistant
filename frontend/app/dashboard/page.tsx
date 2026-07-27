"use client";

import { useEffect, useState, useCallback } from "react";
import { createClient } from "@/lib/supabase";
import { uploadDocument, listDocuments, deleteDocument, getDocumentStatus } from "@/lib/api";
import { useDropzone } from "react-dropzone";
import clsx from "clsx";

interface Document {
  id: string;
  original_name: string;
  file_type: string;
  file_size: number | null;
  status: "processing" | "ready" | "failed";
  chunk_count: number | null;
  error_msg: string | null;
  uploaded_at: string;
}

function formatBytes(bytes: number | null) {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function StatusBadge({ status }: { status: Document["status"] }) {
  if (status === "processing") return (
    <span className="badge-processing">
      <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
      Processing
    </span>
  );
  if (status === "ready") return (
    <span className="badge-ready">
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
      Ready
    </span>
  );
  return (
    <span className="badge-failed">
      <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
      Failed
    </span>
  );
}

function DropZone({ onUpload, uploading }: { onUpload: (file: File) => void; uploading: boolean }) {
  const onDrop = useCallback((files: File[]) => {
    if (files[0]) onUpload(files[0]);
  }, [onUpload]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"], "text/plain": [".txt"] },
    maxFiles: 1,
    disabled: uploading,
  });

  return (
    <div
      {...getRootProps()}
      id="document-dropzone"
      className={clsx(
        "border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-300",
        isDragActive
          ? "border-brand-500 bg-brand-500/10 scale-[1.01]"
          : "border-surface-border hover:border-brand-500/50 hover:bg-surface-elevated",
        uploading && "opacity-50 cursor-not-allowed"
      )}
    >
      <input {...getInputProps()} id="document-file-input" />
      <div className="flex flex-col items-center gap-3">
        <div className={clsx(
          "w-14 h-14 rounded-2xl flex items-center justify-center transition-all",
          isDragActive ? "bg-brand-500/20" : "bg-surface-elevated"
        )}>
          {uploading ? (
            <svg className="w-7 h-7 text-brand-400 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg className="w-7 h-7 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          )}
        </div>
        <div>
          <p className="font-semibold text-white">
            {uploading ? "Uploading…" : isDragActive ? "Drop it here!" : "Drag & drop or click to upload"}
          </p>
          <p className="text-gray-500 text-sm mt-1">PDF, DOCX, TXT — up to 50 MB</p>
        </div>
      </div>
    </div>
  );
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const supabase = createClient();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setToken(data.session?.access_token ?? null);
    });
  }, []);

  const fetchDocuments = useCallback(async () => {
    if (!token) return;
    try {
      const docs = await listDocuments(token);
      setDocuments(docs);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchDocuments();
    const interval = setInterval(fetchDocuments, 5000); // poll every 5s for status
    return () => clearInterval(interval);
  }, [fetchDocuments]);

  async function handleUpload(file: File) {
    if (!token) return;
    setUploading(true);
    setUploadError("");
    try {
      await uploadDocument(file, token);
      await fetchDocuments();
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(docId: string, docName: string) {
    if (!token) return;
    if (!confirm(`Delete "${docName}"? This will remove all its indexed chunks.`)) return;
    try {
      await deleteDocument(docId, token);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  }

  const readyCount = documents.filter((d) => d.status === "ready").length;
  const processingCount = documents.filter((d) => d.status === "processing").length;
  const totalChunks = documents.reduce((sum, d) => sum + (d.chunk_count ?? 0), 0);

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-8 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Document Library</h1>
        <p className="text-gray-400 mt-1 text-sm">
          Upload HR policies, SOPs, and guides. They'll be automatically indexed for AI-powered search.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Indexed Documents", value: readyCount, color: "text-emerald-400" },
          { label: "Processing", value: processingCount, color: "text-amber-400" },
          { label: "Total Chunks", value: totalChunks.toLocaleString(), color: "text-brand-400" },
        ].map((stat) => (
          <div key={stat.label} className="stat-card">
            <p className="text-gray-500 text-xs font-medium uppercase tracking-wider">{stat.label}</p>
            <p className={`text-3xl font-bold ${stat.color}`}>{stat.value}</p>
          </div>
        ))}
      </div>

      {/* Upload */}
      <div className="card p-6 space-y-4">
        <h2 className="font-semibold text-white">Upload Document</h2>
        <DropZone onUpload={handleUpload} uploading={uploading} />
        {uploadError && (
          <div className="bg-red-500/10 border border-red-500/25 rounded-xl p-3 text-red-400 text-sm animate-fade-in">
            {uploadError}
          </div>
        )}
      </div>

      {/* Document list */}
      <div className="card overflow-hidden">
        <div className="px-6 py-4 border-b border-surface-border flex items-center justify-between">
          <h2 className="font-semibold text-white">Documents ({documents.length})</h2>
          <button onClick={fetchDocuments} className="text-gray-500 hover:text-white transition-colors">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16 text-gray-500">
            <svg className="w-5 h-5 animate-spin mr-2" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Loading documents…
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-500">
            <svg className="w-12 h-12 mb-3 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="font-medium">No documents yet</p>
            <p className="text-sm mt-1">Upload your first document above</p>
          </div>
        ) : (
          <div className="divide-y divide-surface-border">
            {documents.map((doc) => (
              <div key={doc.id} id={`doc-row-${doc.id}`}
                   className="flex items-center gap-4 px-6 py-4 hover:bg-surface-elevated/50 transition-colors group">
                {/* File type icon */}
                <div className="w-9 h-9 rounded-lg bg-surface-elevated border border-surface-border flex items-center justify-center shrink-0">
                  <span className="text-xs font-bold text-gray-400 uppercase">{doc.file_type}</span>
                </div>

                {/* Doc info */}
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-white truncate">{doc.original_name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {formatBytes(doc.file_size)} · {formatDate(doc.uploaded_at)}
                    {doc.chunk_count ? ` · ${doc.chunk_count} chunks` : ""}
                  </p>
                  {doc.error_msg && (
                    <p className="text-xs text-red-400 mt-1 truncate">{doc.error_msg}</p>
                  )}
                </div>

                {/* Status */}
                <StatusBadge status={doc.status} />

                {/* Delete */}
                <button
                  id={`delete-doc-${doc.id}`}
                  onClick={() => handleDelete(doc.id, doc.original_name)}
                  className="btn-danger opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Delete document"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
