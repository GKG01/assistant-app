import type { HealthResponse } from "../types/api";

const BASE_URL = "http://127.0.0.1:8000";

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
