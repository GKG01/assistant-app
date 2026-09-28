export interface HealthResponse {
  status: "ok";
  service: "nova-backend";
}

export type BackendStatus = "checking" | "connected" | "offline";
