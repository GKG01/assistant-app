import { useState } from "react";

export function CommandInput() {
  const [command, setCommand] = useState("");
  return (
    <div>
      <div className="flex gap-2 rounded-2xl border border-slate-700 bg-slate-900 p-3">
        <input
          aria-label="Ask Nova"
          placeholder="Ask Nova..."
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          className="min-w-0 flex-1 bg-transparent px-2 text-sm text-slate-100 outline-none focus:ring-2 focus:ring-teal-500 rounded-lg"
        />
        <button disabled title="Microphone coming soon" className="button">
          Mic
        </button>
        <button
          disabled
          title="Agent integration coming soon"
          className="button bg-teal-900"
        >
          Send
        </button>
      </div>
      <p className="mt-3 text-center text-xs text-slate-500">
        Preview only. Commands and voice are coming soon.
      </p>
    </div>
  );
}
