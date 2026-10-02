import { invoke, isTauri } from "@tauri-apps/api/core";

interface DesktopSession {
  token: string;
}

export async function sessionHeaders(): Promise<Record<string, string>> {
  if (!isTauri()) {
    throw new Error(
      "File access requires the Nova desktop app. Start it with npm run tauri dev.",
    );
  }
  // No localStorage, cookies, URL parameters, build-time secrets, or HTTP token endpoint.
  // Ask each time so Rust verifies the owned backend is still running.
  const session = await invoke<DesktopSession>("backend_session");
  return { Authorization: `Bearer ${session.token}`, "X-Nova-Request": "1" };
}
