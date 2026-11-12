import { useLayoutEffect, useRef } from "react";
import type { ChatMessage } from "../../types/chat";
import type { DecideAction } from "./ConfirmationCard";
import { ChatToolStatus } from "./ChatToolStatus";

export function ChatMessageList({
  messages,
  busy,
  decide,
  actionsDisabled,
}: {
  messages: ChatMessage[];
  busy: boolean;
  decide?: DecideAction;
  actionsDisabled?: boolean;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  useLayoutEffect(() => {
    if (viewport.current && nearBottom.current)
      viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [messages, busy]);
  return (
    <div
      ref={viewport}
      role="log"
      aria-label="Conversation"
      aria-live="polite"
      tabIndex={0}
      className="min-h-0 flex-1 space-y-4 overflow-y-auto rounded-xl py-4 [overflow-wrap:anywhere]"
      onScroll={(event) => {
        const node = event.currentTarget;
        nearBottom.current =
          node.scrollHeight - node.scrollTop - node.clientHeight < 80;
      }}
    >
      {messages.length === 0 && (
        <p className="py-8 text-slate-400">
          Ask Nova a question, calculate a value, or find an indexed file.
        </p>
      )}
      {messages.map((message) => (
        <article
          key={message.id}
          aria-label={message.role === "user" ? "You" : "Nova"}
          className={`rounded-xl border p-4 ${message.role === "user" ? "ml-6 border-slate-700 bg-slate-800" : "mr-6 border-teal-900 bg-slate-900"}`}
        >
          <h3 className="mb-2 text-sm font-semibold text-teal-300">
            {message.role === "user" ? "You" : "Nova"}
          </h3>
          <p className="whitespace-pre-wrap text-sm leading-relaxed">
            {message.content}
          </p>
          {message.status === "pending" && (
            <p className="mt-2 text-xs text-slate-400">Sending…</p>
          )}
          {message.status === "failed" && (
            <p className="mt-2 text-xs text-amber-300">
              Request failed. Review the error and verified outcomes before
              sending again.
            </p>
          )}
          {message.toolExecutions && (
            <ChatToolStatus
              records={message.toolExecutions}
              decide={decide}
              disabled={actionsDisabled}
            />
          )}
        </article>
      ))}
      {busy && (
        <p role="status" className="text-sm text-teal-300">
          Nova is processing…
        </p>
      )}
    </div>
  );
}
