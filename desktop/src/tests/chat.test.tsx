import Home from "../pages/Home";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ChatPanel } from "../components/chat/ChatPanel";
import { CommandInput } from "../components/chat/CommandInput";
import { ChatToolStatus } from "../components/chat/ChatToolStatus";
import { ChatMessageList } from "../components/chat/ChatMessageList";
import { AgentError } from "../services/agentContract";
import { sendMessage, clearConversation } from "../services/agentService";
import type { AgentResponse, ToolExecution } from "../types/chat";

vi.mock("../hooks/useBackendStatus", () => ({
  useBackendStatus: () => "connected",
}));
vi.mock("../components/files/FileSearch", () => ({
  FileSearch: () => <p>File search view</p>,
}));
vi.mock("../services/agentService", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  sendMessage: vi.fn(),
  clearConversation: vi.fn(),
}));
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
const cid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const answer = (message = "Hello"): AgentResponse => ({
  conversation_id: cid,
  message,
  tool_executions: [],
  result: null,
  pending_action: null,
});
let host: HTMLDivElement;
let root: Root;
async function render(node: React.ReactNode) {
  await act(async () => root.render(node));
}
async function click(text: string) {
  const button = [...host.querySelectorAll("button")].find(
    (b) => b.textContent === text,
  )!;
  expect(button).toBeDefined();
  await act(async () => button.click());
}
async function input(text: string) {
  const field = host.querySelector("textarea")!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    )!.set!.call(field, text);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
beforeEach(() => {
  vi.mocked(sendMessage).mockReset().mockResolvedValue(answer());
  vi.mocked(clearConversation).mockReset().mockResolvedValue();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
});

it("renders empty chat, labels and whitespace rejection", async () => {
  await render(<ChatPanel />);
  expect(host.textContent).toContain("Ask Nova a question");
  expect(host.querySelector("label")?.htmlFor).toBe("chat-input");
  await input("   ");
  await click("Send");
  expect(sendMessage).not.toHaveBeenCalled();
});
it("trims text, renders real response, reuses ID and clears through backend", async () => {
  await render(<ChatPanel />);
  await input(" Hello ");
  await click("Send");
  expect(sendMessage).toHaveBeenCalledWith(
    "Hello",
    undefined,
    expect.any(AbortSignal),
  );
  expect(host.querySelector('[aria-label="Nova"]')?.textContent).toContain(
    "Hello",
  );
  await input("Next");
  await click("Send");
  expect(sendMessage).toHaveBeenLastCalledWith(
    "Next",
    cid,
    expect.any(AbortSignal),
  );
  await click("New Conversation");
  expect(clearConversation).toHaveBeenCalledWith(cid, expect.any(AbortSignal));
  expect(host.querySelectorAll("article")).toHaveLength(0);
  await input("Fresh");
  await click("Send");
  expect(sendMessage).toHaveBeenLastCalledWith(
    "Fresh",
    undefined,
    expect.any(AbortSignal),
  );
});
it("prevents duplicate click, repeated Enter and reset while sending", async () => {
  const pending = deferred<AgentResponse>();
  vi.mocked(sendMessage).mockReturnValue(pending.promise);
  await render(<ChatPanel />);
  await input("Wait");
  await act(async () => {
    const send = [...host.querySelectorAll("button")].find(
      (b) => b.textContent === "Send",
    )!;
    send.click();
    send.click();
  });
  await click("New Conversation");
  const field = host.querySelector("textarea")!;
  await act(async () => {
    for (let i = 0; i < 3; i++)
      field.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
      );
  });
  expect(sendMessage).toHaveBeenCalledTimes(1);
  expect(clearConversation).not.toHaveBeenCalled();
  expect(host.textContent).toContain("Nova is processing");
  await act(async () => pending.resolve(answer("Done")));
  expect(field.disabled).toBe(false);
});
it("rejects overlong input including paste without truncating it", async () => {
  await render(<ChatPanel />);
  await input("x".repeat(10001));
  await click("Send");
  expect(sendMessage).not.toHaveBeenCalled();
  expect(host.querySelector("textarea")?.getAttribute("aria-invalid")).toBe(
    "true",
  );
});
it("composer supports Enter, Shift+Enter and IME safely", async () => {
  const send = vi.fn();
  await render(
    <CommandInput
      value="hello"
      onChange={vi.fn()}
      onSend={send}
      disabled={false}
    />,
  );
  const field = host.querySelector("textarea")!;
  const key = async (options: KeyboardEventInit) =>
    act(async () => {
      field.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Enter",
          bubbles: true,
          cancelable: true,
          ...options,
        }),
      );
    });
  await key({ shiftKey: true });
  await key({ isComposing: true });
  await act(async () => {
    field.dispatchEvent(
      new CompositionEvent("compositionstart", { bubbles: true }),
    );
  });
  await key({});
  expect(send).not.toHaveBeenCalled();
  await act(async () => {
    field.dispatchEvent(
      new CompositionEvent("compositionend", { bubbles: true }),
    );
  });
  await key({});
  expect(send).toHaveBeenCalledTimes(1);
});

it.each([0, 404, 409, 502, 503, 504])(
  "shows failure %i without fabricated assistant or replay",
  async (status) => {
    vi.mocked(sendMessage).mockRejectedValue(
      new AgentError("Safe failure", status),
    );
    await render(<ChatPanel />);
    await input("Open it");
    await click("Send");
    expect(host.querySelector('[role="alert"]')?.textContent).toContain(
      "Safe failure",
    );
    expect(host.querySelector('[aria-label="You"]')?.textContent).toContain(
      "Open it",
    );
    expect(host.querySelector('[aria-label="Nova"]')).toBeNull();
    expect(sendMessage).toHaveBeenCalledTimes(1);
  },
);
it("preserves session and messages when clearing fails, then permits retry", async () => {
  await render(<ChatPanel />);
  await input("Hello");
  await click("Send");
  vi.mocked(clearConversation).mockRejectedValueOnce(
    new AgentError("busy", 409),
  );
  await click("New Conversation");
  expect(host.textContent).toContain("conversation was preserved");
  expect(host.querySelectorAll("article")).toHaveLength(2);
  await click("New Conversation");
  expect(host.querySelectorAll("article")).toHaveLength(0);
});
it("clears missing/expired sessions without replaying the old request", async () => {
  await render(<ChatPanel />);
  await input("Hello");
  await click("Send");
  vi.mocked(sendMessage).mockRejectedValueOnce(new AgentError("Expired", 404));
  await input("Open it");
  await click("Send");
  vi.mocked(clearConversation).mockRejectedValueOnce(
    new AgentError("Gone", 404),
  );
  await click("New Conversation");
  expect(host.querySelectorAll("article")).toHaveLength(0);
  expect(sendMessage).toHaveBeenCalledTimes(2);
});
it("aborts on unmount and ignores delayed old responses in a fresh mounted chat", async () => {
  const pending = deferred<AgentResponse>();
  vi.mocked(sendMessage).mockReturnValueOnce(pending.promise);
  await render(<ChatPanel />);
  await input("Wait");
  await click("Send");
  const signal = vi.mocked(sendMessage).mock.calls[0][2];
  await render(<div />);
  expect(signal.aborted).toBe(true);
  await render(<ChatPanel />);
  await act(async () => pending.resolve(answer("Stale")));
  expect(host.textContent).not.toContain("Stale");
  expect(host.querySelectorAll("article")).toHaveLength(0);
});

const record = (changes: Partial<ToolExecution> = {}): ToolExecution => ({
  tool_call_id: "call",
  tool_name: "search_files",
  executed: true,
  state: "completed",
  arguments_validated: true,
  permission_approved: true,
  confirmation_required: false,
  result: { success: true, status: "SUCCESS" },
  ...changes,
});
it("renders verified file order safely and never creates action buttons", async () => {
  const rows = ["z<script>alert(1)</script>.txt", "a.txt"].map(
    (name, index) => ({
      id: index + 1,
      name,
      path: name,
      extension: ".txt",
      size: 4,
      created_at: "2026-01-01",
      modified_at: "2026-01-01",
      indexed_at: "2026-01-01",
    }),
  );
  await render(
    <ChatToolStatus
      records={[record({ result: { success: true, data: { results: rows } } })]}
    />,
  );
  expect([...host.querySelectorAll("h3")].map((h) => h.textContent)).toEqual(
    rows.map((r) => r.name),
  );
  expect(host.querySelector("script")).toBeNull();
  expect(host.querySelector("button")).toBeNull();
});
it.each([
  [
    record({ confirmation_required: true, executed: false }),
    "Confirmation required",
  ],
  [record({ state: "rejected", executed: false }), "Request rejected"],
  [record({ state: "failed" }), "Operation failed"],
  [record(), "Operation completed"],
  [record({ result: { status: "PERMISSION_DENIED" } }), "Permission denied"],
] as const)("grounds tool status", async (execution, expected) => {
  await render(<ChatToolStatus records={[execution]} />);
  expect(host.textContent).toContain(expected);
});
it("escapes assistant HTML and keeps older-message scroll position", async () => {
  const messages = [
    {
      id: "1",
      role: "assistant" as const,
      status: "completed" as const,
      content: '<img src=x onerror="alert(1)">',
    },
  ];
  await render(<ChatMessageList messages={messages} busy={false} />);
  expect(host.querySelector("img")).toBeNull();
  expect(host.textContent).toContain("<img");
  const log = host.querySelector('[role="log"]')! as HTMLDivElement;
  Object.defineProperties(log, {
    scrollHeight: { value: 1000 },
    clientHeight: { value: 200 },
  });
  log.scrollTop = 50;
  await act(async () => log.dispatchEvent(new Event("scroll")));
  await render(
    <ChatMessageList
      messages={[...messages, { ...messages[0], id: "2" }]}
      busy={true}
    />,
  );
  expect(log.scrollTop).toBe(50);
});
it("retains conversation ID and verified outcomes on provider failure", async () => {
  vi.mocked(sendMessage).mockRejectedValueOnce(
    new AgentError("Provider failed after calculation", 502, cid, [
      record({ tool_name: "calculate" }),
    ]),
  );
  await render(<ChatPanel />);
  await input("Calculate");
  await click("Send");
  expect(host.textContent).toContain("calculate: Operation completed");
  await input("Hello");
  await click("Send");
  expect(sendMessage).toHaveBeenLastCalledWith(
    "Hello",
    cid,
    expect.any(AbortSignal),
  );
});

it("caps visible history at 100 messages until explicit reset", async () => {
  await render(<ChatPanel />);
  for (let i = 0; i < 50; i++) {
    await input(`Message ${i}`);
    await click("Send");
  }
  expect(host.querySelectorAll("article")).toHaveLength(100);
  expect(host.querySelector("textarea")?.disabled).toBe(true);
  await click("New Conversation");
  expect(host.querySelector("textarea")?.disabled).toBe(false);
});

it("scrolls new messages when already near the bottom", async () => {
  await render(<ChatMessageList messages={[]} busy={false} />);
  const log = host.querySelector('[role="log"]')! as HTMLDivElement;
  Object.defineProperties(log, {
    scrollHeight: { value: 1000 },
    clientHeight: { value: 200 },
  });
  log.scrollTop = 790;
  await act(async () => log.dispatchEvent(new Event("scroll")));
  await render(
    <ChatMessageList
      messages={[
        { id: "new", role: "assistant", content: "Hello", status: "completed" },
      ]}
      busy={false}
    />,
  );
  expect(log.scrollTop).toBe(1000);
});

it("preserves pending chat and session across rapid navigation", async () => {
  const pending = deferred<AgentResponse>();
  vi.mocked(sendMessage).mockReturnValueOnce(pending.promise);
  await render(<Home />);
  await input("Hello");
  await click("Send");
  await click("Files");
  await click("Chat");
  await click("Files");
  await act(async () => pending.resolve(answer("Returned while hidden")));
  await click("Chat");
  expect(host.textContent).toContain("Returned while hidden");
  await input("Follow up");
  await click("Send");
  expect(sendMessage).toHaveBeenLastCalledWith(
    "Follow up",
    cid,
    expect.any(AbortSignal),
  );
});
