import { screen, waitFor, within } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import {
  API,
  apiError,
  CONV_A,
  CONV_B,
  message,
  MODEL_BIG,
  PROJECT_ID,
  preview,
  sse,
} from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";

const chatUrl = (id: string) => `/projects/${PROJECT_ID}/c/${id}`;
const START = {
  message_id: "m2",
  user_message_id: "m1",
  conversation_id: CONV_A,
  model_id: "x",
  sources: [],
};
const END = {
  message_id: "m2",
  usage: { input_tokens: 1, output_tokens: 2, cost_usd: null, latency_ms: 5 },
};

/** A response body you feed by hand: push SSE text, close it, or leave it open. */
function controlledStream() {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  return {
    body,
    push: (text: string) => {
      controller.enqueue(encoder.encode(text));
    },
    close: () => {
      controller.close();
    },
  };
}

function sseResponse(body: ReadableStream<Uint8Array> | string) {
  return new HttpResponse(body, { headers: { "Content-Type": "text/event-stream" } });
}

async function typeAndSend(user: ReturnType<typeof renderApp>["user"], text: string) {
  const box = await screen.findByRole("textbox", { name: "Message" });
  await user.type(box, text);
  await user.click(screen.getByRole("button", { name: "Send" }));
}

describe("chat", () => {
  it("shows streamed tokens in order, then the saved reply", async () => {
    const stream = controlledStream();
    let saved = false;
    server.use(
      http.post(`${API}/api/v1/conversations/${CONV_A}/messages`, () => sseResponse(stream.body)),
      http.get(`${API}/api/v1/conversations/${CONV_A}/messages`, () =>
        HttpResponse.json(
          saved
            ? [message("m1", 1, "user", "Hi"), message("m2", 2, "assistant", "Hello there")]
            : [],
        ),
      ),
    );
    const { user } = renderApp(chatUrl(CONV_A));
    await typeAndSend(user, "Hi");

    stream.push(sse(["message_start", START], ["delta", { text: "Hel" }]));
    const log = screen.getByRole("log", { name: "Messages" });
    await within(log).findByText("Hel");
    stream.push(sse(["delta", { text: "lo there" }]));
    await within(log).findByText("Hello there");
    // A second send is blocked while the reply streams.
    expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();

    saved = true;
    stream.push(sse(["message_end", END]));
    stream.close();
    await screen.findByRole("button", { name: "Send" });
    expect(within(log).getByText("Hello there")).toBeInTheDocument();
    expect(within(log).getAllByRole("article")).toHaveLength(2);
  });

  it("stop aborts the request and shows the partial reply as incomplete", async () => {
    const stream = controlledStream();
    let aborted = false;
    let saved = false;
    server.use(
      http.post(`${API}/api/v1/conversations/${CONV_A}/messages`, ({ request }) => {
        request.signal.addEventListener("abort", () => {
          aborted = true;
          saved = true;
        });
        return sseResponse(stream.body);
      }),
      http.get(`${API}/api/v1/conversations/${CONV_A}/messages`, () =>
        HttpResponse.json(
          saved
            ? [
                message("m1", 1, "user", "Hi"),
                message("m2", 2, "assistant", "Partial", "cancelled"),
              ]
            : [],
        ),
      ),
    );
    const { user } = renderApp(chatUrl(CONV_A));
    await typeAndSend(user, "Hi");
    stream.push(sse(["message_start", START], ["delta", { text: "Partial" }]));
    await screen.findByText("Partial");
    await user.click(screen.getByRole("button", { name: "Stop" }));

    await screen.findByText(/Stopped\. The part that arrived is kept/);
    await waitFor(() => {
      expect(aborted).toBe(true);
    });
    expect(await screen.findByText("incomplete")).toBeInTheDocument();
  });

  it("an error mid-stream keeps the text and offers models without switching", async () => {
    const switchSpy = vi.fn();
    server.use(
      http.post(`${API}/api/v1/conversations/${CONV_A}/messages`, () =>
        sseResponse(
          sse(
            ["message_start", START],
            ["delta", { text: "Half an ans" }],
            [
              "error",
              {
                message_id: "m2",
                code: "rate_limited",
                message: "The provider is rate limiting requests.",
                details: {
                  suggested_models: [
                    {
                      model_id: MODEL_BIG,
                      display_name: "Big Model",
                      provider: "openai",
                      context_window: 1e6,
                    },
                  ],
                },
              },
            ],
          ),
        ),
      ),
      http.post(`${API}/api/v1/conversations/${CONV_A}/switch-model`, () => {
        switchSpy();
        return HttpResponse.json({});
      }),
      http.get(`${API}/api/v1/conversations/${CONV_A}/handoff-preview`, () =>
        HttpResponse.json(preview(MODEL_BIG)),
      ),
    );
    const { user } = renderApp(chatUrl(CONV_A));
    await typeAndSend(user, "Hi");
    expect(await screen.findByText("The provider is rate limiting requests.")).toBeInTheDocument();
    const offer = screen.getByRole("button", { name: "Big Model" });
    await user.click(offer);
    // Picking a suggestion opens the preview; nothing is switched until the user confirms.
    expect(await screen.findByRole("dialog", { name: "Switch to Big Model" })).toBeInTheDocument();
    expect(switchSpy).not.toHaveBeenCalled();
  });

  it("shows warning events as banners", async () => {
    server.use(
      http.post(`${API}/api/v1/conversations/${CONV_A}/messages`, () =>
        sseResponse(
          sse(
            ["message_start", START],
            [
              "warning",
              {
                message_id: "m2",
                code: "retrieval_failed",
                message: "Project code was not used: the embedding call failed (rate_limited).",
                details: {},
              },
            ],
            ["delta", { text: "ok" }],
            ["message_end", END],
          ),
        ),
      ),
    );
    const { user } = renderApp(chatUrl(CONV_A));
    await typeAndSend(user, "Hi");
    const warning = await screen.findByText(/Project code was not used/);
    expect(warning.closest("[role=alert]")).toHaveTextContent("Warning:");
  });

  it("explains a 409 generation in progress", async () => {
    server.use(
      http.post(`${API}/api/v1/conversations/${CONV_A}/messages`, () =>
        HttpResponse.json(
          apiError("generation_in_progress", "A reply is already being generated."),
          { status: 409 },
        ),
      ),
    );
    const { user } = renderApp(chatUrl(CONV_A));
    await typeAndSend(user, "Hi");
    expect(
      await screen.findByText(/A reply is already being generated for this conversation/),
    ).toBeInTheDocument();
    // The input is free again: nothing is stuck.
    expect(screen.getByRole("textbox", { name: "Message" })).toBeEnabled();
  });

  it("ContextTooLong shows suggested models and never switches by itself", async () => {
    const switchSpy = vi.fn();
    server.use(
      http.post(`${API}/api/v1/conversations/${CONV_A}/messages`, () =>
        HttpResponse.json(
          apiError("context_too_long", "The request is too long for this model.", {
            suggested_models: [
              {
                model_id: MODEL_BIG,
                display_name: "Big Model",
                provider: "openai",
                context_window: 1e6,
              },
            ],
          }),
          { status: 413 },
        ),
      ),
      http.post(`${API}/api/v1/conversations/${CONV_A}/switch-model`, () => {
        switchSpy();
        return HttpResponse.json({});
      }),
    );
    const { user } = renderApp(chatUrl(CONV_A));
    await typeAndSend(user, "a very long question");
    expect(await screen.findByText("The request is too long for this model.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Big Model" })).toBeInTheDocument();
    await delay(50);
    expect(switchSpy).not.toHaveBeenCalled();
  });

  it("ignores a slow answer for the previous conversation after navigation", async () => {
    server.use(
      http.get(`${API}/api/v1/conversations/${CONV_A}/messages`, async () => {
        await delay(150);
        return HttpResponse.json([message("old", 1, "user", "OLD CONVERSATION TEXT")]);
      }),
      http.get(`${API}/api/v1/conversations/${CONV_B}/messages`, () =>
        HttpResponse.json([message("new", 1, "user", "Second conversation text")]),
      ),
    );
    const { user } = renderApp(chatUrl(CONV_A));
    const nav = await screen.findByRole("navigation", { name: "Projects and conversations" });
    await user.click(await within(nav).findByRole("link", { name: "Second chat" }));
    await screen.findByText("Second conversation text");
    await delay(250);
    expect(screen.queryByText("OLD CONVERSATION TEXT")).not.toBeInTheDocument();
  });

  it("renders model Markdown without raw HTML and with safe links", async () => {
    server.use(
      http.get(`${API}/api/v1/conversations/${CONV_A}/messages`, () =>
        HttpResponse.json([
          message(
            "m",
            1,
            "assistant",
            'See [docs](https://example.com) <img src=x onerror="alert(1)"> <b>bold?</b>\n\n```py\nprint(1)\n```\n\nمرحبا بالعالم',
          ),
        ]),
      ),
    );
    renderApp(chatUrl(CONV_A));
    const link = await screen.findByRole("link", { name: "docs" });
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAttribute("target", "_blank");
    const log = screen.getByRole("log", { name: "Messages" });
    expect(log.querySelector("img")).toBeNull();
    expect(log.querySelector("b")).toBeNull();
    expect(screen.getByRole("button", { name: "Copy code" })).toBeInTheDocument();
    expect(screen.getByText("مرحبا بالعالم").closest("[dir=auto]")).not.toBeNull();
  });
});
