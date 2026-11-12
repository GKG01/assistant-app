import {
  AgentError,
  executions,
  isObject,
  validConversationId,
} from "./agentContract";
import type {
  FileActionResponse,
  HealthResponse,
  IndexStats,
  SearchFilters,
  SearchResponse,
} from "../types/api";
import { sessionHeaders } from "./session";

const BASE_URL = "http://127.0.0.1:8000";

async function fileRequest<T>(
  path: string,
  method = "GET",
  timeout = 30000,
): Promise<T> {
  const response = await fetch(`${BASE_URL}/files${path}`, {
    method,
    headers: await sessionHeaders(),
    signal: AbortSignal.timeout(timeout),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : (detail?.message ??
          (Array.isArray(detail)
            ? "Invalid search filters. Check the values and try again."
            : "File request failed.")),
    );
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

export async function healthCheck(
  signal?: AbortSignal,
): Promise<HealthResponse> {
  const headers = await sessionHeaders();
  const authenticated = await fetch(`${BASE_URL}/session`, {
    headers,
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(4000)])
      : AbortSignal.timeout(4000),
  });
  if (!authenticated.ok) throw new Error("Desktop session is unavailable.");
  const response = await fetch(`${BASE_URL}/health`, {
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(4000)])
      : AbortSignal.timeout(4000),
  });
  if (!response.ok) throw new Error("Backend health check failed.");
  const data: unknown = await response.json();
  if (
    typeof data !== "object" ||
    data === null ||
    !("status" in data) ||
    data.status !== "ok" ||
    !("service" in data) ||
    data.service !== "nova-backend"
  )
    throw new Error("Unexpected health response.");
  return data as HealthResponse;
}

// Same URL and per-request managed-session credential as the existing file client.
export async function agentRequest(
  path: string,
  body: Record<string, string>,
  signal: AbortSignal,
): Promise<unknown> {
  const combined = AbortSignal.any([
    signal,
    AbortSignal.timeout(path === "/conversation/clear" ? 30000 : 660000),
  ]);
  try {
    const response = await fetch(`${BASE_URL}/agent${path}`, {
      method: "POST",
      headers: {
        ...(await sessionHeaders()),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: combined,
    });
    const data: unknown = await response.json();
    if (!response.ok) {
      const payload = isObject(data) ? data : {};
      const id = validConversationId(payload.conversation_id)
        ? payload.conversation_id
        : undefined;
      const records =
        payload.tool_executions === undefined
          ? []
          : executions(payload.tool_executions);
      const fallback: Record<number, string> = {
        401: "Desktop session unavailable. Restart Nova.",
        403: "Request denied by backend policy.",
        404: "Conversation unavailable or expired. Start a new conversation and search again.",
        409: "This conversation is busy. Wait before trying again.",
        422: "Invalid message or conversation ID. Check your input.",
        429: "AI provider rate limit reached. Try again later.",
        502: "AI provider could not complete the request.",
        503: "AI provider is unavailable or not configured. Check backend configuration.",
        504: "AI provider timed out. The request may have performed operations.",
      };
      // Only the backend's sanitized agent error detail; never raw validation bodies.
      const detail =
        [429, 502, 503, 504].includes(response.status) &&
        typeof payload.detail === "string"
          ? payload.detail
          : (fallback[response.status] ?? "Agent request failed.");
      const actionStatus =
        path.startsWith("/actions/") &&
        ["expired", "cancelled", "completed", "failed"].includes(
          String(payload.action_status),
        )
          ? String(payload.action_status)
          : undefined;
      throw new AgentError(
        actionStatus
          ? `Action is ${actionStatus}; it cannot execute again.`
          : detail,
        response.status,
        id,
        records,
        actionStatus,
      );
    }
    return data;
  } catch (error) {
    if (error instanceof AgentError) throw error;
    throw new AgentError(
      combined.aborted
        ? "Request timed out or was interrupted. Backend operations may still finish; do not blindly resend."
        : "Could not reach Nova's managed backend or read its response. Start or restart the desktop app. The request outcome is unknown.",
    );
  }
}
