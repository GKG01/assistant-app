import { CommandInput } from "../components/chat/CommandInput";
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
      <section className="flex flex-1 flex-col items-center justify-center py-20 text-center" aria-labelledby="welcome">
        <div aria-hidden="true" className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl border border-teal-800 bg-teal-950 text-2xl text-teal-300">N</div>
        <p className="mb-3 text-xs uppercase tracking-widest text-teal-400">Your local assistant</p>
        <h2 id="welcome" className="text-3xl font-medium tracking-tight sm:text-4xl">What can I help you with?</h2>
        <p className="mt-4 max-w-md text-sm leading-6 text-slate-400">
          A foundation for finding files and getting everyday tasks done, with you in control.
        </p>
      </section>
      <footer><CommandInput /></footer>
    </main>
  );
}
