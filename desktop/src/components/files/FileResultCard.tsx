import type { IndexedFile } from "../../types/api";
import { formatBytes, formatDate } from "../../utils/format";

interface Props {
  file: IndexedFile;
  busy: boolean;
  onAction: (id: number, action: "open" | "reveal") => void;
}

export function FileResultCard({ file, busy, onAction }: Props) {
  return (
    <li className="rounded-xl border border-slate-700 bg-slate-900 p-4">
      <h3 className="break-words font-medium">{file.name}</h3>
      <p className="mt-1 text-xs text-slate-400">
        {file.extension.slice(1).toUpperCase() || "File"} · {formatBytes(file.size)} · Modified {formatDate(file.modified_at)}
      </p>
      <p className="mt-2 break-all text-xs text-slate-500">{file.path}</p>
      <div className="mt-3 flex gap-2">
        <button className="button bg-teal-900 hover:bg-teal-800" disabled={busy}
          onClick={() => onAction(file.id, "open")} aria-label={`Open ${file.name}`}>Open</button>
        <button className="button bg-slate-800 hover:bg-slate-700" disabled={busy}
          onClick={() => onAction(file.id, "reveal")} aria-label={`Show ${file.name} in folder`}>Show in Folder</button>
      </div>
    </li>
  );
}
