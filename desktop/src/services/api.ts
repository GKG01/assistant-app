import type { FileActionResponse, HealthResponse, IndexStats, SearchFilters, SearchResponse } from "../types/api";

const BASE_URL = "http://127.0.0.1:8000";

async function fileRequest<T>(path: string, method = "GET", timeout = 30000): Promise<T> {
  const response = await fetch(`${BASE_URL}/files${path}`, {
    method,
    headers: { "X-Nova-Request": "1" },
    signal: AbortSignal.timeout(timeout),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === "string" ? detail
      : detail?.message ?? (Array.isArray(detail) ? "Invalid search filters. Check the values and try again." : "File request failed."));
  }
  return data as T;
}

export function indexFiles(): Promise<IndexStats> {
  return fileRequest("/index", "POST", 600000);
}

export function searchFiles(filters: SearchFilters): Promise<SearchResponse> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  return fileRequest(`/search?${query}`);
}

export function openFile(id: number): Promise<FileActionResponse> {
  return fileRequest(`/${id}/open`, "POST");
}

export function showInFolder(id: number): Promise<FileActionResponse> {
  return fileRequest(`/${id}/reveal`, "POST");
}

export async function healthCheck(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${BASE_URL}/health`, {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(4000)]) : AbortSignal.timeout(4000),
  });
  if (!response.ok) throw new Error("Backend health check failed.");
  const data: unknown = await response.json();
  if (
    typeof data !== "object" || data === null ||
    !("status" in data) || data.status !== "ok" ||
    !("service" in data) || data.service !== "nova-backend"
  ) throw new Error("Unexpected health response.");
  return data as HealthResponse;
}
