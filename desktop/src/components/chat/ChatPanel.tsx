import { useState } from "react";
import { useChat } from "../../hooks/useChat";
import { ChatMessageList } from "./ChatMessageList";
import { CommandInput } from "./CommandInput";

export function ChatPanel() {
  const chat = useChat();
  const [draft, setDraft] = useState("");
  const busy = chat.state !== "idle";
  async function send() {
    const submitted = draft;
    // Clear only an accepted submission, and never overwrite a newer draft.
    if (await chat.send(submitted))
      setDraft((previous) => (previous === submitted ? "" : previous));
  }
  return (
    <section
      aria-label="Chat with Nova"
      className="flex h-[calc(100dvh-13rem)] min-h-80 flex-col gap-3"
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-medium">Chat with Nova</h2>
        <button
          className="button bg-slate-800 hover:bg-slate-700"
          disabled={busy}
          title={
            busy
              ? "Wait for the request to finish before clearing context"
              : undefined
          }
          onClick={async () => {
            if (await chat.reset()) setDraft("");
          }}
        >
          New Conversation
        </button>
      </header>
      <ChatMessageList
        messages={chat.messages}
        busy={chat.state === "sending"}
      />
      {chat.state === "clearing" && (
        <p role="status">Clearing backend context…</p>
      )}
      {chat.error && (
        <p
          role="alert"
          className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded-lg border border-amber-800 p-3 text-sm text-amber-200 [overflow-wrap:anywhere]"
        >
          {chat.error}
        </p>
      )}
      {chat.blocked && (
        <p className="text-sm text-amber-200">
          Start a new conversation to continue. Requests are never automatically
          replayed.
        </p>
      )}
      {!busy && !chat.blocked && chat.messages.at(-1)?.status === "failed" && (
        <button
          className="button self-start bg-slate-800"
          onClick={() => setDraft(chat.messages.at(-1)!.content)}
        >
          Edit failed message before resending
        </button>
      )}
      <CommandInput
        value={draft}
        onChange={setDraft}
        onSend={() => void send()}
        disabled={busy || chat.blocked}
      />
    </section>
  );
}
