import { ConfirmationCard, type DecideAction } from "./ConfirmationCard";
import type { ToolExecution } from "../../types/chat";
import type { IndexedFile } from "../../types/api";
import { isObject } from "../../services/agentService";
import { FileResultCard } from "../files/FileResultCard";

function files(record: ToolExecution): IndexedFile[] {
  if (
    !record.executed ||
    record.state !== "completed" ||
    record.result.success !== true
  )
    return [];
  const data = record.result.data;
  const rows =
    record.tool_name === "search_files" && isObject(data)
      ? data.results
      : record.tool_name === "get_file_info"
        ? [data]
        : [];
  if (!Array.isArray(rows) || rows.length > 50) return [];
  // Reject the entire set rather than dropping rows and changing ordinal references.
  if (
    !rows.every(
      (row) =>
        isObject(row) &&
        typeof row.id === "number" &&
        [
          "name",
          "extension",
          "path",
          "created_at",
          "modified_at",
          "indexed_at",
        ].every((key) => typeof row[key] === "string") &&
        typeof row.size === "number",
    )
  )
    return [];
  return rows as IndexedFile[];
}

export function toolStatus(record: ToolExecution): string {
  if (record.result.status === "INDEX_SYNC_FAILED")
    return "Filesystem completed; index synchronization failed. Refresh the index.";
  if (record.result.status === "CANCELLED")
    return "Cancelled — no filesystem mutation.";
  if (
    ["create_folder", "rename_file", "move_file"].includes(record.tool_name) &&
    record.confirmation_required
  )
    return "Write proposal — see confirmation status below.";
  if (
    record.confirmation_required ||
    record.result.status === "CONFIRMATION_REQUIRED"
  )
    return "Confirmation required — not executed. Approval is not available in chat yet.";
  if (record.result.status === "PERMISSION_DENIED")
    return "Permission denied — not executed.";
  if (record.state === "rejected") return "Request rejected — not executed.";
  if (record.state === "failed" || record.result.success === false)
    return "Operation failed.";
  if (
    record.executed &&
    record.state === "completed" &&
    record.result.success === true
  ) {
    if (["open_file", "show_in_folder"].includes(record.tool_name))
      return "Windows accepted the request; application rendering is not verified.";
    if (record.result.status === "NO_RESULTS")
      return "Completed — no matching files.";
    return "Operation completed.";
  }
  return record.state === "started"
    ? "Execution started; completion unverified."
    : "Requested; execution unverified.";
}

export function ChatToolStatus({
  records,
  decide,
  disabled,
}: {
  records: ToolExecution[];
  decide?: DecideAction;
  disabled?: boolean;
}) {
  return (
    <div className="mt-3 space-y-3">
      {records.map((record, index) => {
        const rows = files(record);
        return (
          <section
            key={`${record.tool_call_id}-${index}`}
            aria-label={`Tool ${record.tool_name}`}
          >
            <p className="text-sm text-teal-200">
              {record.tool_name}: {toolStatus(record)}
            </p>
            <ConfirmationCard
              data={record.result.data}
              decide={decide}
              disabled={disabled}
            />
            {rows.length > 0 && (
              <>
                <p className="my-2 text-xs text-slate-400">
                  Verified indexed metadata. Follow-ups use the latest lookup,
                  in this order.
                </p>
                <ol className="list-inside list-decimal space-y-2">
                  {rows.map((file) => (
                    <FileResultCard key={file.id} file={file} />
                  ))}
                </ol>
              </>
            )}
          </section>
        );
      })}
    </div>
  );
}
