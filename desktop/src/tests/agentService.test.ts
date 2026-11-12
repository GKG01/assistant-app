import { afterEach, expect, it, vi } from "vitest";
import { sendMessage, clearConversation } from "../services/agentService";
vi.mock("../services/session", () => ({
  sessionHeaders: vi.fn(async () => ({
    Authorization: "Bearer test-only",
    "X-Nova-Request": "1",
  })),
}));
const cid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const payload = {
  conversation_id: cid,
  message: "1000",
  result: null,
  pending_action: null,
  tool_executions: [],
};
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it("uses real contract, central URL and session headers", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(payload)))
    .mockResolvedValueOnce(new Response(JSON.stringify(payload)))
    .mockResolvedValueOnce(new Response('{"status":"cleared"}'));
  vi.stubGlobal("fetch", fetcher);
  const signal = new AbortController().signal;
  expect(await sendMessage("125 * 8", undefined, signal)).toEqual(payload);
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
    message: "125 * 8",
  });
  expect(fetcher.mock.calls[0][1].headers).toEqual({
    Authorization: "Bearer test-only",
    "X-Nova-Request": "1",
    "Content-Type": "application/json",
  });
  await sendMessage("Next", cid, signal);
  expect(JSON.parse(fetcher.mock.calls[1][1].body).conversation_id).toBe(cid);
  await clearConversation(cid, signal);
  expect(fetcher.mock.calls[2][0]).toMatch(/\/agent\/conversation\/clear$/);
});
it.each([
  {},
  { ...payload, conversation_id: "fake" },
  { ...payload, tool_executions: [{}] },
])("rejects malformed success", async (data) => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(data))),
  );
  await expect(
    sendMessage("Hello", undefined, new AbortController().signal),
  ).rejects.toThrow("Unexpected backend response");
});
it("rejects mismatched session IDs", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(payload))),
  );
  await expect(
    sendMessage(
      "Hello",
      "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      new AbortController().signal,
    ),
  ).rejects.toThrow("Unexpected");
});
it.each([401, 403, 404, 409, 422, 429, 502, 503, 504])(
  "handles HTTP %i without retry",
  async (status) => {
    const fetcher = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            detail:
              status >= 429
                ? "Safe provider error"
                : [{ input: "private input" }],
          }),
          { status },
        ),
    );
    vi.stubGlobal("fetch", fetcher);
    await expect(
      sendMessage("Hello", cid, new AbortController().signal),
    ).rejects.toMatchObject({ status });
    expect(fetcher).toHaveBeenCalledTimes(1);
  },
);
it("retains partial failure ID and records", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            detail: "Safe failure",
            conversation_id: cid,
            tool_executions: [],
          }),
          { status: 504 },
        ),
    ),
  );
  await expect(
    sendMessage("Hello", undefined, new AbortController().signal),
  ).rejects.toMatchObject({ conversationId: cid, toolExecutions: [] });
});
it("handles disconnection without raw diagnostics", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new Error("secret transport details");
    }),
  );
  await expect(
    sendMessage("Hello", cid, new AbortController().signal),
  ).rejects.toThrow("outcome is unknown");
});
it("handles abort/timeout without replay", async () => {
  const controller = new AbortController();
  controller.abort();
  const fetcher = vi.fn(async () => {
    throw new DOMException("Aborted", "AbortError");
  });
  vi.stubGlobal("fetch", fetcher);
  await expect(sendMessage("Hello", cid, controller.signal)).rejects.toThrow(
    "Backend operations may still finish",
  );
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it("rejects mismatched error session without overwriting active context", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            detail: "Safe error",
            conversation_id: cid,
            tool_executions: [],
          }),
          { status: 504 },
        ),
    ),
  );
  await expect(
    sendMessage(
      "Hello",
      "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      new AbortController().signal,
    ),
  ).rejects.toThrow("Unexpected backend conversation");
});

it("confirms only the stored ID using authenticated headers and conversation binding", async () => {
  const { decideAction } = await import("../services/agentService");
  const aid = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  const fetcher = vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          conversation_id: cid,
          action: { action_id: aid, conversation_id: cid, status: "completed" },
          message: "Completed",
          tool_executions: [],
        }),
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  await decideAction(aid, cid, "confirm", new AbortController().signal);
  expect(fetcher.mock.calls[0]).toBeDefined();
  const options = (
    fetcher.mock.calls as unknown as [string, RequestInit][]
  )[0][1];
  expect(JSON.parse(String(options.body))).toEqual({ conversation_id: cid });
  expect(options.headers).toMatchObject({
    Authorization: "Bearer test-only",
    "X-Nova-Request": "1",
  });
});

it("preserves structured expiration and rejects cross-conversation action responses", async () => {
  const { decideAction } = await import("../services/agentService");
  const aid = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({ detail: "Expired", action_status: "expired" }),
          { status: 409 },
        ),
    ),
  );
  await expect(
    decideAction(aid, cid, "confirm", new AbortController().signal),
  ).rejects.toMatchObject({ status: 409, actionStatus: "expired" });
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            conversation_id: aid,
            action: {
              action_id: aid,
              conversation_id: aid,
              status: "completed",
            },
            message: "Completed",
            tool_executions: [],
          }),
        ),
    ),
  );
  await expect(
    decideAction(aid, cid, "confirm", new AbortController().signal),
  ).rejects.toThrow("could not be verified");
});
