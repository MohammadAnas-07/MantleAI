import { afterEach, describe, expect, it, vi } from "vitest";

import { sendMessage, toStreamEvent } from "./endpoints";
import type { StreamEvent } from "./types";

afterEach(() => {
  vi.unstubAllGlobals();
});

function sseResponse(text: string): Response {
  return new Response(text, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

describe("chat stream", () => {
  it("turns SSE messages into typed events and skips unknown ones", () => {
    expect(toStreamEvent({ event: "delta", data: '{"text":"a"}' })).toEqual({
      type: "delta",
      data: { text: "a" },
    });
    expect(toStreamEvent({ event: "ping", data: "{}" })).toBeNull();
    expect(toStreamEvent({ event: "delta", data: "not json" })).toBeNull();
    expect(toStreamEvent({ event: "delta", data: "3" })).toBeNull();
  });

  it("streams events in order", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          sseResponse(
            'event: message_start\ndata: {"message_id":"m","sources":[]}\n\n' +
              'event: warning\ndata: {"code":"retrieval_failed","message":"w"}\n\n' +
              'event: delta\ndata: {"text":"Hel"}\n\nevent: delta\ndata: {"text":"lo"}\n\n' +
              'event: message_end\ndata: {"message_id":"m","usage":{}}\n\n',
          ),
        ),
    );
    const events: StreamEvent[] = [];
    await sendMessage("c1", "hi", (e) => events.push(e), new AbortController().signal);
    expect(events.map((e) => e.type)).toEqual([
      "message_start",
      "warning",
      "delta",
      "delta",
      "message_end",
    ]);
  });

  it("rejects before streaming on an HTTP error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "generation_in_progress", message: "A reply is already running." },
          }),
          { status: 409 },
        ),
      ),
    );
    await expect(
      sendMessage("c1", "hi", () => undefined, new AbortController().signal),
    ).rejects.toMatchObject({ status: 409, code: "generation_in_progress" });
  });
});
