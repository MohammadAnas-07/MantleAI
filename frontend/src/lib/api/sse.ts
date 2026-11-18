// Server-sent events over a fetch response. EventSource can't send a POST body, so the chat
// reply (POST /conversations/{id}/messages) is read with a stream reader and parsed here.
//
// The parser follows the SSE format: lines end in \n, \r\n or \r; "event:" and "data:" set
// fields (several data lines join with \n); a line starting with ":" is a comment; a blank
// line ends the event. Network chunks can end anywhere, also inside a line or inside a
// multi-byte character, so text is decoded in streaming mode and partial lines are kept.

import { ApiError, CLIENT_CODES } from "./errors";

export interface SseMessage {
  event: string;
  data: string;
}

export class SseParser {
  private buffer = "";
  private event = "";
  private data: string[] = [];
  private sawCr = false;

  /** Feed decoded text; returns the events completed by it. */
  feed(text: string): SseMessage[] {
    const out: SseMessage[] = [];
    let input = text;
    // A \r at the end of the previous piece may be the first half of \r\n.
    if (this.sawCr && input.startsWith("\n")) input = input.slice(1);
    this.sawCr = false;
    this.buffer += input;

    for (;;) {
      const match = /\r\n|\r|\n/.exec(this.buffer);
      if (!match) break;
      // A lone \r at the very end might still become \r\n: wait for more input.
      if (match[0] === "\r" && match.index === this.buffer.length - 1) {
        this.sawCr = true;
        this.line(this.buffer.slice(0, match.index), out);
        this.buffer = "";
        break;
      }
      this.line(this.buffer.slice(0, match.index), out);
      this.buffer = this.buffer.slice(match.index + match[0].length);
    }
    return out;
  }

  /** The stream ended: an event without its final blank line is dropped, as the spec says. */
  end(): void {
    this.buffer = "";
    this.event = "";
    this.data = [];
  }

  private line(line: string, out: SseMessage[]): void {
    if (line === "") {
      if (this.data.length > 0 || this.event !== "") {
        out.push({ event: this.event || "message", data: this.data.join("\n") });
      }
      this.event = "";
      this.data = [];
      return;
    }
    if (line.startsWith(":")) return; // comment or keep-alive
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.event = value;
    else if (field === "data") this.data.push(value);
    // "id" and "retry" don't apply to a one-off POST stream.
  }
}

/**
 * Read `body` to the end and call `onMessage` for every event, in order. Stops with an
 * ApiError("aborted") when `signal` fires.
 */
export async function readSse(
  body: ReadableStream<Uint8Array>,
  onMessage: (message: SseMessage) => void,
  signal?: AbortSignal,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  const parser = new SseParser();
  const abort = (): void => {
    void reader.cancel().catch(() => undefined);
  };
  signal?.addEventListener("abort", abort, { once: true });
  try {
    for (;;) {
      if (signal?.aborted) throw new ApiError(0, CLIENT_CODES.aborted, "The reply was stopped.");
      let result: ReadableStreamReadResult<Uint8Array>;
      try {
        result = await reader.read();
      } catch {
        if (signal?.aborted) throw new ApiError(0, CLIENT_CODES.aborted, "The reply was stopped.");
        throw new ApiError(0, CLIENT_CODES.network, "The connection to the Mantle API broke.");
      }
      // Cancelling the reader on abort makes a pending read finish as "done": check first.
      if (signal?.aborted) throw new ApiError(0, CLIENT_CODES.aborted, "The reply was stopped.");
      if (result.done) {
        for (const message of parser.feed(decoder.decode())) onMessage(message);
        parser.end();
        return;
      }
      for (const message of parser.feed(decoder.decode(result.value, { stream: true }))) {
        onMessage(message);
      }
    }
  } finally {
    signal?.removeEventListener("abort", abort);
    reader.releaseLock();
  }
}
