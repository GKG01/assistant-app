import { useState } from "react";
import { ChatPanel } from "../components/chat/ChatPanel";
import { FileSearch } from "../components/files/FileSearch";
import { StatusIndicator } from "../components/ui/StatusIndicator";
import { useBackendStatus } from "../hooks/useBackendStatus";
import { isTauri } from "@tauri-apps/api/core";

export default function Home() {
  const status = useBackendStatus();
  const [page, setPage] = useState<"chat" | "files">("chat");
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col px-6 py-6 sm:px-10">
      <header className="flex items-center justify-between border-b border-slate-800 pb-5">
        <h1 className="text-xl font-semibold tracking-tight">
          Nova<span className="text-teal-400">.</span>
        </h1>
        <StatusIndicator status={status} />
      </header>
      {!isTauri() && (
        <p role="status" className="mt-4 text-sm text-amber-300">
          Browser preview only. Start Nova with npm run tauri dev to access
          files.
        </p>
      )}
      <nav aria-label="Main navigation" className="my-4 flex gap-2">
        <button
          className="button bg-slate-800"
          aria-pressed={page === "chat"}
          onClick={() => setPage("chat")}
        >
          Chat
        </button>
        <button
          className="button bg-slate-800"
          aria-pressed={page === "files"}
          onClick={() => setPage("files")}
        >
          Files
        </button>
      </nav>
      <div hidden={page !== "chat"}>
        <ChatPanel />
      </div>
      <div hidden={page !== "files"}>
        <FileSearch />
      </div>
    </main>
  );
}
