import { useEffect, useRef } from "react";
import { MAX_MESSAGE_LENGTH } from "../../services/agentService";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled: boolean;
}

export function CommandInput({ value, onChange, onSend, disabled }: Props) {
  const composing = useRef(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const wasDisabled = useRef(disabled);
  useEffect(() => {
    if (
      wasDisabled.current &&
      !disabled &&
      input.current?.getClientRects().length
    )
      input.current.focus();
    wasDisabled.current = disabled;
  }, [disabled]);
  const length = [...value.trim()].length;
  const invalid = length > MAX_MESSAGE_LENGTH;
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (!disabled && length > 0 && !invalid) onSend();
      }}
    >
      <label htmlFor="chat-input" className="mb-2 block text-sm">
        Message Nova
      </label>
      <div className="flex items-end gap-2 rounded-2xl border border-slate-700 bg-slate-900 p-3">
        <textarea
          ref={input}
          id="chat-input"
          rows={3}
          maxLength={20000}
          value={value}
          disabled={disabled}
          aria-describedby="composer-help"
          aria-invalid={invalid}
          placeholder="Ask Nova…"
          onChange={(event) => onChange(event.target.value)}
          onCompositionStart={() => {
            composing.current = true;
          }}
          onCompositionEnd={() => {
            composing.current = false;
          }}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !composing.current &&
              !event.nativeEvent.isComposing &&
              event.keyCode !== 229
            ) {
              event.preventDefault();
              if (!disabled && length > 0 && !invalid) onSend();
            }
          }}
          className="min-w-0 flex-1 resize-y rounded-lg bg-transparent p-2 text-sm disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={disabled || !length || invalid}
          className="button bg-teal-800 hover:bg-teal-700"
        >
          Send
        </button>
      </div>
      <p
        id="composer-help"
        className={`mt-2 text-xs ${invalid ? "text-amber-300" : "text-slate-400"}`}
      >
        Enter to send · Shift+Enter for a newline · {length.toLocaleString()}
        /10,000 characters
      </p>
    </form>
  );
}
