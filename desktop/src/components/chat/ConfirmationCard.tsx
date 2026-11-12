import { isObject } from "../../services/agentService";
import { validConversationId } from "../../services/agentContract";

export type DecideAction = (
  actionId: string,
  decision: "confirm" | "cancel",
) => void;

// Keep whitespace, control and formatting characters visible instead of allowing
// a filename to rearrange or hide the path being approved. Escape literal
// backslashes too, so a literal escape sequence cannot impersonate a character.
const displayPath = (path: string) =>
  JSON.stringify(path).replace(/[\p{Cc}\p{Cf}\p{Z}]/gu, (char) => {
    const point = char.codePointAt(0)!;
    return point > 0xffff
      ? `\\u{${point.toString(16)}}`
      : `\\u${point.toString(16).padStart(4, "0")}`;
  });

export function ConfirmationCard({
  data,
  decide,
  disabled,
}: {
  data: unknown;
  decide?: DecideAction;
  disabled?: boolean;
}) {
  if (!isObject(data) || !isObject(data.pending_action)) return null;
  const action = data.pending_action;
  if (
    !validConversationId(action.action_id) ||
    !validConversationId(action.conversation_id) ||
    !["create_folder", "rename_file", "move_file"].includes(
      String(action.tool_name),
    ) ||
    ![
      "pending",
      "confirming",
      "cancelling",
      "completed",
      "cancelled",
      "expired",
      "failed",
    ].includes(String(action.status)) ||
    typeof action.destination_path !== "string" ||
    action.destination_path.length === 0 ||
    typeof action.expires_at !== "string" ||
    !(action.tool_name === "create_folder"
      ? action.source_path === null
      : typeof action.source_path === "string" && action.source_path.length > 0)
  )
    return null;
  const id = action.action_id;
  return (
    <section
      aria-label="Review filesystem action"
      className="my-3 space-y-2 rounded-lg border border-amber-600 p-3"
    >
      <p>{String(action.tool_name)}</p>
      {typeof action.source_path === "string" && (
        <p className="break-all" dir="ltr">
          Source: <code>{displayPath(action.source_path)}</code>
        </p>
      )}
      <p className="break-all" dir="ltr">
        Destination: <code>{displayPath(action.destination_path)}</code>
      </p>
      <p role="status">
        {String(action.status)} · Expires {action.expires_at}
      </p>
      <p className="text-xs">
        One operation. Existing files will never be overwritten.
      </p>
      {action.status === "pending" && decide && (
        <div className="flex gap-2">
          <button
            className="button bg-teal-800"
            disabled={disabled}
            onClick={() => decide(id, "confirm")}
          >
            Confirm
          </button>
          <button
            className="button bg-slate-700"
            disabled={disabled}
            onClick={() => decide(id, "cancel")}
          >
            Cancel
          </button>
        </div>
      )}
    </section>
  );
}
