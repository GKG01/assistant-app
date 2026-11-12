export interface ToolExecution {
  tool_call_id: string;
  tool_name: string;
  executed: boolean;
  arguments_validated: boolean;
  permission_approved: boolean;
  confirmation_required: boolean;
  state: "requested" | "rejected" | "started" | "completed" | "failed";
  result: Record<string, unknown>;
}

export interface AgentResponse {
  conversation_id: string;
  message: string;
  result: unknown;
  pending_action: unknown;
  tool_executions: ToolExecution[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "pending" | "completed" | "failed";
  toolExecutions?: ToolExecution[];
}
