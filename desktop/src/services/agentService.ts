import { agentRequest } from "./api";
import type { AgentResponse } from "../types/chat";
import {
  AgentError,
  executions,
  isObject,
  validConversationId,
} from "./agentContract";
export { AgentError, MAX_MESSAGE_LENGTH, isObject } from "./agentContract";

export async function sendMessage(
  message: string,
  conversationId: string | undefined,
  signal: AbortSignal,
): Promise<AgentResponse> {
  const data = await agentRequest(
    "/message",
    {
      message,
      ...(conversationId ? { conversation_id: conversationId } : {}),
    },
    signal,
  ).catch((error: unknown) => {
    if (
      error instanceof AgentError &&
      conversationId &&
      error.conversationId &&
      error.conversationId !== conversationId
    )
      throw new AgentError(
        "Unexpected backend conversation. Start a new conversation before continuing.",
      );
    throw error;
  });
  if (
    !isObject(data) ||
    !validConversationId(data.conversation_id) ||
    typeof data.message !== "string" ||
    (conversationId && data.conversation_id !== conversationId)
  )
    throw new AgentError(
      "Unexpected backend response. Start a new conversation before continuing.",
    );
  try {
    return {
      ...data,
      tool_executions: executions(data.tool_executions),
    } as unknown as AgentResponse;
  } catch {
    throw new AgentError(
      "Unexpected backend response. Start a new conversation before continuing.",
    );
  }
}

export async function clearConversation(
  conversationId: string,
  signal: AbortSignal,
): Promise<void> {
  const data = await agentRequest(
    "/conversation/clear",
    { conversation_id: conversationId },
    signal,
  );
  if (!isObject(data) || data.status !== "cleared")
    throw new AgentError("Backend context clearing could not be verified.");
}

export async function decideAction(
  actionId: string,
  conversationId: string,
  decision: "confirm" | "cancel",
  signal: AbortSignal,
) {
  if (!validConversationId(actionId) || !validConversationId(conversationId))
    throw new AgentError("Invalid action reference.");
  const data = await agentRequest(
    `/actions/${actionId}/${decision}`,
    { conversation_id: conversationId },
    signal,
  );
  if (
    !isObject(data) ||
    data.conversation_id !== conversationId ||
    !isObject(data.action) ||
    data.action.action_id !== actionId ||
    data.action.conversation_id !== conversationId ||
    typeof data.message !== "string" ||
    !["completed", "cancelled", "expired", "failed"].includes(
      String(data.action.status),
    )
  )
    throw new AgentError(
      "Action outcome could not be verified. Inspect the filesystem before making a new request.",
    );
  return {
    action: data.action,
    message: data.message,
    records: executions(data.tool_executions),
  };
}
