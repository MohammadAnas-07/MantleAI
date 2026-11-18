import { describe, expect, it } from "vitest";

import { ApiError } from "./errors";
import { readSse, SseParser, type SseMessage } from "./sse";

function streamOf(pieces: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const piece of pieces) {
        controller.enqueue(typeof piece === "string" ? encoder.encode(piece) : piece);
      }
      controller.close();
    },
  });
}

async function collect(pieces: (string | Uint8Array)[]): Promise<SseMessage[]> {
  const out: SseMessage[] = [];
  await readSse(streamOf(pieces), (m) => out.push(m));
  return out;
}

describe("SseParser", () => {
  it("parses events with event and data fields", () => {
    const parser = new SseParser();
    const out = parser.feed(
      'event: delta\ndata: {"text":"hi"}\n\nevent: message_end\ndata: {}\n\n',
    );
    expect(out).toEqual([
      { event: "delta", data: '{"text":"hi"}' },
      { event: "message_end", data: "{}" },
    ]);
  });

  it("joins several data lines and defaults the event name", () => {
    expect(new SseParser().feed("data: a\ndata: b\n\n")).toEqual([
      { event: "message", data: "a\nb" },
    ]);
  });

  it("ignores comments, unknown fields and extra blank lines", () => {
    const out = new SseParser().feed(
      ": keep-alive\n\n\nid: 7\nretry: 100\nevent: delta\ndata: x\n\n",
    );
    expect(out).toEqual([{ event: "delta", data: "x" }]);
  });

  it("keeps a value's own spaces after the first one", () => {
    expect(new SseParser().feed("data:  two spaces\n\n")[0]?.data).toBe(" two spaces");
    expect(new SseParser().feed("data:no space\n\n")[0]?.data).toBe("no space");
  });

  it("handles CRLF and lone CR line endings, also split between pieces", () => {
    const parser = new SseParser();
    expect(parser.feed("event: delta\r")).toEqual([]);
    expect(parser.feed("\ndata: a\r\n\r")).toEqual([{ event: "delta", data: "a" }]);
    expect(parser.feed("\ndata: b\r\r")).toEqual([{ event: "message", data: "b" }]);
  });

  it("drops an event that never got its blank line", () => {
    const parser = new SseParser();
    expect(parser.feed("event: delta\ndata: half")).toEqual([]);
    parser.end();
    expect(parser.feed("\n\n")).toEqual([]);
  });
});

describe("readSse", () => {
  it("handles events split across network pieces at any byte", async () => {
    const text = 'event: delta\ndata: {"text":"one"}\n\nevent: delta\ndata: {"text":"two"}\n\n';
    const bytes = new TextEncoder().encode(text);
    for (let cut = 1; cut < bytes.length; cut += 7) {
      const out = await collect([bytes.slice(0, cut), bytes.slice(cut)]);
      expect(out.map((m) => m.data)).toEqual(['{"text":"one"}', '{"text":"two"}']);
    }
  });

  it("decodes multi-byte characters split across pieces", async () => {
    const text = 'event: delta\ndata: {"text":"नमस्ते 👋 مرحبا"}\n\n';
    const bytes = new TextEncoder().encode(text);
    const pieces = Array.from(bytes, (b) => new Uint8Array([b])); // one byte at a time
    const [message] = await collect(pieces);
    expect(JSON.parse(message?.data ?? "{}")).toEqual({ text: "नमस्ते 👋 مرحبا" });
  });

  it("delivers an error event in the middle of a stream in order", async () => {
    const out = await collect([
      'event: message_start\ndata: {"message_id":"m"}\n\n',
      'event: delta\ndata: {"text":"par"}\n\n',
      'event: error\ndata: {"code":"rate_limited"}\n\n',
    ]);
    expect(out.map((m) => m.event)).toEqual(["message_start", "delta", "error"]);
  });

  it("stops with an aborted ApiError when the signal fires", async () => {
    const controller = new AbortController();
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(encoder.encode("event: delta\ndata: x\n\n"));
        // never closes: a reply still streaming
      },
    });
    const seen: string[] = [];
    const done = readSse(
      body,
      (m) => {
        seen.push(m.data);
        controller.abort();
      },
      controller.signal,
    );
    await expect(done).rejects.toMatchObject({ code: "aborted" });
    await expect(done).rejects.toBeInstanceOf(ApiError);
    expect(seen).toEqual(["x"]);
  });

  it("reports a broken connection as a network error", async () => {
    const body = new ReadableStream<Uint8Array>({
      pull(c) {
        c.error(new Error("socket closed"));
      },
    });
    await expect(readSse(body, () => undefined)).rejects.toMatchObject({ code: "network_error" });
  });
});
