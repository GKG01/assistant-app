import { useEffect, useRef, useState } from "react";
import {
  AgentError,
  clearConversation,
  MAX_MESSAGE_LENGTH,
  sendMessage,
} from "../services/agentService";
import type { ChatMessage } from "../types/chat";

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string>();
  const [state, setState] = useState<"idle" | "sending" | "clearing">("idle");
  const [error, setError] = useState("");
  const [blocked, setBlocked] = useState(false);
  const active = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      active.current?.abort();
      active.current = null;
    };
  }, []);

  async function send(raw: string): Promise<boolean> {
    const content = raw.trim();
    if (active.current || blocked || messages.length >= 100) return false;
    if (!content || [...content].length > MAX_MESSAGE_LENGTH) {
      setError("Enter a message between 1 and 10,000 characters.");
      return false;
    }
    const controller = new AbortController();
    active.current = controller;
    const current = () => mounted.current && active.current === controller;
    const id = crypto.randomUUID();
    setMessages((previous) => [
      ...previous,
      { id, role: "user", content, status: "pending" },
    ]);
    setState("sending");
    setError("");
    try {
      const result = await sendMessage(
        content,
        conversationId,
        controller.signal,
      );
      if (!current()) return false;
      setConversationId(result.conversation_id);
      setMessages((previous) => [
        ...previous.map((message) =>
          message.id === id
            ? { ...message, status: "completed" as const }
            : message,
        ),
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: result.message,
          status: "completed",
          toolExecutions: result.tool_executions,
        },
      ]);
    } catch (caught) {
      if (!current()) return false;
      const failure =
        caught instanceof AgentError
          ? caught
          : new AgentError("Request failed; the outcome is unknown.");
      if (failure.conversationId) setConversationId(failure.conversationId);
      setBlocked([0, 401, 404, 422].includes(failure.status));
      setError(failure.message);
      setMessages((previous) =>
        previous.map((message) =>
          message.id === id
            ? {
                ...message,
                status: "failed",
                toolExecutions: failure.toolExecutions,
              }
            : message,
        ),
      );
    } finally {
      if (current()) {
        active.current = null;
        setState("idle");
      }
    }
    return true;
  }

  async function reset(): Promise<boolean> {
    // Clearing a busy server session is rejected. Wait for the current request.
    if (active.current) return false;
    const controller = new AbortController();
    active.current = controller;
    const current = () => mounted.current && active.current === controller;
    setState("clearing");
    setError("");
    try {
      if (conversationId) {
        try {
          await clearConversation(conversationId, controller.signal);
        } catch (caught) {
          // Missing/expired context is already unavailable; never replay the old turn.
          if (!(caught instanceof AgentError && caught.status === 404))
            throw caught;
        }
      }
      if (!current()) return false;
      setConversationId(undefined);
      setMessages([]);
      setBlocked(false);
      return true;
    } catch {
      if (current())
        setError(
          "Could not clear backend context. This conversation was preserved. Try New Conversation again when the backend is available.",
        );
      return false;
    } finally {
      if (current()) {
        active.current = null;
        setState("idle");
      }
    }
  }
  return {
    messages,
    state,
    error,
    blocked: blocked || messages.length >= 100,
    send,
    reset,
  };
}
