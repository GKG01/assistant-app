import type { BackendStatus } from "../../types/api";

export function StatusIndicator({ status }: { status: BackendStatus }) {
  const labels = {
    checking: "Checking…",
    connected: "Connected",
    offline: "Offline",
  };
  return (
    <span
      className="flex items-center gap-2 text-xs text-slate-400"
      role="status"
    >
      <span
        aria-hidden="true"
        className={`h-2 w-2 rounded-full ${status === "connected" ? "bg-emerald-400" : "bg-slate-500"}`}
      />
      Backend: {labels[status]}
    </span>
  );
}
