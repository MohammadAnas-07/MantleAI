import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch, buildUrl } from "./client";
import { ApiError, errorFromBody, errorMessage, fieldErrors } from "./errors";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ApiError mapping", () => {
  it("reads the backend's error shape", () => {
    const error = errorFromBody(409, {
      error: { code: "dependency_cycle", message: "That would loop.", details: { a: 1 } },
    });
    expect(error).toMatchObject({ status: 409, code: "dependency_cycle", details: { a: 1 } });
    expect(error.message).toBe("That would loop.");
  });

  it("still gives a message for unknown shapes", () => {
    expect(errorFromBody(500, "Internal Server Error")).toMatchObject({
      code: "http_error",
      message: "Request failed (500).",
    });
    expect(errorFromBody(502, { error: { code: 5 } }).code).toBe("http_error");
  });

  it("maps validation errors to fields", () => {
    const error = errorFromBody(422, {
      error: {
        code: "validation_error",
        message: "Invalid request.",
        details: {
          errors: [
            { loc: ["body", "title"], msg: "Value error, must not be empty", type: "value_error" },
            { loc: ["body", "title"], msg: "second", type: "x" },
            { loc: ["body"], msg: "send at least one field", type: "value_error" },
          ],
        },
      },
    });
    expect(fieldErrors(error)).toEqual({ title: "must not be empty" });
    const withField = errorFromBody(422, {
      error: { code: "invalid_query", message: "The query is empty.", details: { field: "query" } },
    });
    expect(fieldErrors(withField)).toEqual({ query: "The query is empty." });
    expect(fieldErrors(new Error("x"))).toEqual({});
    expect(errorMessage(new Error("secret text"))).toBe("Something went wrong.");
  });
});

describe("apiFetch", () => {
  it("builds URLs with query parameters and skips empty ones", () => {
    const url = new URL(buildUrl("/api/v1/x", { a: 1, b: null, c: undefined, d: "x y" }));
    expect(url.pathname).toBe("/api/v1/x");
    expect([...url.searchParams]).toEqual([
      ["a", "1"],
      ["d", "x y"],
    ]);
  });

  it("sends JSON with a content type on writes, {} when there is no body", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(json({ ok: true })));
    vi.stubGlobal("fetch", fetchMock);
    await apiFetch("/api/v1/x", { method: "POST" });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.body).toBe("{}");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    await apiFetch("/api/v1/x");
    const getInit = fetchMock.mock.calls[1]?.[1] as RequestInit;
    expect(getInit.body).toBeUndefined();
  });

  it("returns undefined for 204", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(apiFetch("/api/v1/x", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("throws the backend's error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ error: { code: "not_found", message: "Nope." } }, 404)),
    );
    await expect(apiFetch("/api/v1/x")).rejects.toMatchObject({ status: 404, code: "not_found" });
  });

  it("reports an unreachable backend as a network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await apiFetch("/api/v1/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).isNetwork).toBe(true);
    expect((error as ApiError).message).toBe("Can't reach the Mantle API.");
  });

  it("times out", async () => {
    vi.stubGlobal("fetch", hangingFetch());
    await expect(apiFetch("/api/v1/x", { timeoutMs: 20 })).rejects.toMatchObject({
      code: "timeout",
    });
  });

  it("stops when the caller aborts", async () => {
    vi.stubGlobal("fetch", hangingFetch());
    const controller = new AbortController();
    const pending = apiFetch("/api/v1/x", { signal: controller.signal });
    controller.abort();
    const error = await pending.catch((e: unknown) => e);
    expect((error as ApiError).isAbort).toBe(true);
  });

  it("reports an unreadable body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not json", { status: 200 })));
    await expect(apiFetch("/api/v1/x")).rejects.toMatchObject({ code: "bad_response" });
  });
});

/** A fetch that only settles when its signal aborts, like a server that never answers. */
function hangingFetch() {
  return vi.fn(
    (_url: string, init: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        });
      }),
  );
}
