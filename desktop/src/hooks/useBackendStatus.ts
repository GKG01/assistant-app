import { useEffect, useState } from "react";
import { healthCheck } from "../services/api";
import type { BackendStatus } from "../types/api";

export function useBackendStatus(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>("checking");
  useEffect(() => {
    const controller = new AbortController();
    const check = async () => {
      try {
        await healthCheck(controller.signal);
        if (!controller.signal.aborted) setStatus("connected");
      } catch {
        if (!controller.signal.aborted) setStatus("offline");
      }
    };
    void check();
    const interval = window.setInterval(() => void check(), 10000);
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, []);
  return status;
}
