import type { ToolExecution } from "../types/chat";
export const MAX_MESSAGE_LENGTH = 10000;
export const validConversationId = (value: unknown): value is string =>
  typeof value === "string" &&
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
    value,
  );

export function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function executions(value: unknown): ToolExecution[] {
  if (!Array.isArray(value) || value.length > 10)
    throw new Error("Invalid records");
  for (const record of value) {
    if (
      !isObject(record) ||
      typeof record.tool_call_id !== "string" ||
      typeof record.tool_name !== "string" ||
      !isObject(record.result) ||
      !["requested", "rejected", "started", "completed", "failed"].includes(
        String(record.state),
      ) ||
      [
        "executed",
        "arguments_validated",
        "permission_approved",
        "confirmation_required",
      ].some((key) => typeof record[key] !== "boolean")
    )
      throw new Error("Invalid records");
  }
  return value as ToolExecution[];
}

export class AgentError extends Error {
  constructor(
    message: string,
    public status = 0,
    public conversationId?: string,
    public toolExecutions: ToolExecution[] = [],
  ) {
    super(message);
  }
}
