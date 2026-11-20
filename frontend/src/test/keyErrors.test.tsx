// Saved provider keys that the current MASTER_ENCRYPTION_KEY can't decrypt (audit A-004):
// each screen says so and says what to do, instead of "API unreachable". MSW only.

import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { API, CONV_A, PROJECT_ID, sse } from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";
import { agentRun, RUN_ID } from "./workflowFixtures";

const RAW = "upstream said: secret prompt text";

function credential(readable: boolean) {
  return {
    id: "c1",
    provider: "google",
    label: "main",
    key_hint: "1234",
    last_tested_at: null,
    last_test_ok: null,
    created_at: "2026-11-20T10:00:00Z",
    readable,
  };
}

describe("unreadable provider keys", () => {
  it("warns on every page when /health reports unreadable keys", async () => {
    server.use(
      http.get(`${API}/health`, () =>
        HttpResponse.json({ status: "ok", database: "up", keys: "unreadable" }),
      ),
    );
    renderApp("/");
    const banner = await screen.findByText(/can't be decrypted with the current/);
    expect(banner).toHaveTextContent("MASTER_ENCRYPTION_KEY");
    expect(banner.closest("[role=alert]")).toHaveTextContent(/enter .*keys again/i);
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
  });

  it("explains the chat error with what to do", async () => {
    server.use(
      http.post(
        `${API}/api/v1/conversations/${CONV_A}/messages`,
        () =>
          new HttpResponse(
            sse(
              [
                "message_start",
                {
                  message_id: "m2",
                  user_message_id: "m1",
                  conversation_id: CONV_A,
                  model_id: "x",
                  sources: [],
                },
              ],
              [
                "error",
                { message_id: "m2", code: "credential_unreadable", message: RAW, details: {} },
              ],
            ),
            { headers: { "Content-Type": "text/event-stream" } },
          ),
      ),
    );
    const { user } = renderApp(`/projects/${PROJECT_ID}/c/${CONV_A}`);
    await user.type(await screen.findByRole("textbox", { name: "Message" }), "Hi");
    await user.click(screen.getByRole("button", { name: "Send" }));
    const text = await screen.findByText(
      /can't be decrypted with the current MASTER_ENCRYPTION_KEY/,
    );
    expect(text).toHaveTextContent(/enter the key again in Settings/);
    expect(document.body).not.toHaveTextContent(RAW);
  });

  it("marks the key in settings and explains a failed test", async () => {
    server.use(
      http.get(`${API}/api/v1/credentials`, () => HttpResponse.json([credential(false)])),
      http.post(`${API}/api/v1/credentials/c1/test`, () =>
        HttpResponse.json({
          ok: false,
          error_code: "credential_unreadable",
          model_id: "x",
          tested_at: "2026-11-20T10:00:00Z",
        }),
      ),
    );
    const { user } = renderApp("/settings");
    const row = (await screen.findByText("main")).closest("li") as HTMLElement;
    expect(within(row).getByText("can't be read")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Test" }));
    const failed = await screen.findByText(/^The test failed:/);
    expect(failed).toHaveTextContent(/can't be decrypted with the current MASTER_ENCRYPTION_KEY/);
    expect(screen.queryByText(/credential_unreadable/)).not.toBeInTheDocument();
  });

  it("explains it on a failed agent run", async () => {
    const failed = agentRun("failed", { error: "credential_unreadable", error_message: RAW });
    server.use(
      http.get(`${API}/api/v1/projects/${PROJECT_ID}/agent-runs`, () =>
        HttpResponse.json({ items: [failed] }),
      ),
      http.get(`${API}/api/v1/agent-runs/${RUN_ID}`, () => HttpResponse.json(failed)),
    );
    renderApp(`/projects/${PROJECT_ID}/workflow`);
    expect(
      await screen.findByText(/can't be decrypted with the current MASTER_ENCRYPTION_KEY/),
    ).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(RAW);
  });

  it("shows our words, not provider text, for a provider failure in chat", async () => {
    server.use(
      http.post(
        `${API}/api/v1/conversations/${CONV_A}/messages`,
        () =>
          new HttpResponse(
            sse([
              "error",
              { message_id: "m2", code: "provider_unavailable", message: RAW, details: {} },
            ]),
            { headers: { "Content-Type": "text/event-stream" } },
          ),
      ),
    );
    const { user } = renderApp(`/projects/${PROJECT_ID}/c/${CONV_A}`);
    await user.type(await screen.findByRole("textbox", { name: "Message" }), "Hi");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/did not answer/)).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(RAW);
  });
});
