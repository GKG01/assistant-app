import { CommandInput } from "../components/chat/CommandInput";
import { FileSearch } from "../components/files/FileSearch";
import { StatusIndicator } from "../components/ui/StatusIndicator";
import { useBackendStatus } from "../hooks/useBackendStatus";

export default function Home() {
  const status = useBackendStatus();
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col px-6 py-6 sm:px-10">
      <header className="flex items-center justify-between border-b border-slate-800 pb-5">
        <h1 className="text-xl font-semibold tracking-tight">Nova<span className="text-teal-400">.</span></h1>
        <StatusIndicator status={status} />
      </header>
      <FileSearch />
      <footer><CommandInput /></footer>
    </main>
  );
}
