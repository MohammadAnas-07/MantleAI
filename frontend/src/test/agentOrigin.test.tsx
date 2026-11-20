import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { UsageSection } from "../features/settings/UsageSection";
import { API, MODEL_SMALL, PROJECT_ID } from "./fixtures";
import { renderApp, renderWithClient } from "./render";
import { server } from "./server";
import { DECISION_ID, memoryItem, RUN_ID } from "./workflowFixtures";

const proposed = memoryItem(DECISION_ID, "decision", "Use argon2", {
  status: "proposed",
  source: "agent",
  source_agent_run_id: RUN_ID,
  stage_key: "requirements",
});

function withDecisions(items = [proposed]) {
  server.use(
    http.get(`${API}/api/v1/projects/${PROJECT_ID}/memory`, ({ request }) => {
      const kind = new URL(request.url).searchParams.get("kind");
      const found = kind === "decision" ? items : [];
      return HttpResponse.json({ items: found, total: found.length, limit: 100, offset: 0 });
    }),
  );
}

describe("memory items from agent runs", () => {
  it("shows a badge and links to the run", async () => {
    withDecisions([proposed, memoryItem("x1", "decision", "Typed by hand")]);
    renderApp(`/projects/${PROJECT_ID}`);
    const card = (await screen.findByText("Use argon2")).closest("article") as HTMLElement;
    expect(within(card).getByText("from agent run")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Open the agent run" })).toHaveAttribute(
      "href",
      `/projects/${PROJECT_ID}/workflow?run=${RUN_ID}`,
    );
    const manual = screen.getByText("Typed by hand").closest("article") as HTMLElement;
    expect(within(manual).queryByText("from agent run")).not.toBeInTheDocument();
  });

  it("lets the user accept a proposed decision", async () => {
    withDecisions();
    const bodies: unknown[] = [];
    server.use(
      http.patch(`${API}/api/v1/memory/${DECISION_ID}`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ ...proposed, status: "accepted" });
      }),
    );
    const { user } = renderApp(`/projects/${PROJECT_ID}`);
    await user.click(await screen.findByRole("button", { name: "Accept Use argon2" }));
    await waitFor(() => {
      expect(bodies).toEqual([{ status: "accepted" }]);
    });
    expect(screen.getByRole("button", { name: "Reject Use argon2" })).toBeInTheDocument();
  });
});

describe("agent run usage", () => {
  it("shows the agent_run purpose in the activity panel", async () => {
    server.use(
      http.get(`${API}/api/v1/usage/records`, () =>
        HttpResponse.json([
          {
            id: "u1",
            created_at: new Date().toISOString(),
            model_id: MODEL_SMALL,
            purpose: "agent_run",
            trigger: "user",
            status: "success",
            error_code: null,
            input_tokens: 1200,
            output_tokens: 300,
            cost_usd: "0.002",
            latency_ms: 900,
            project_id: PROJECT_ID,
            conversation_id: null,
          },
        ]),
      ),
    );
    const { user } = renderApp(`/projects/${PROJECT_ID}`);
    await user.click(await screen.findByRole("button", { name: /Show Activity/ }));
    const table = await screen.findByRole("table", { name: "Model calls this session" });
    expect(await within(table).findByText("agent run")).toBeInTheDocument();
  });

  it("lists agent runs on their own line in the usage view", async () => {
    server.use(
      http.get(`${API}/api/v1/usage`, () =>
        HttpResponse.json({
          total_calls: 3,
          total_input_tokens: 3000,
          total_output_tokens: 600,
          total_cost_usd: "0.006",
          lines: [
            {
              model_id: MODEL_SMALL,
              purpose: "agent_run",
              trigger: "user",
              calls: 2,
              input_tokens: 2000,
              output_tokens: 500,
              cost_usd: "0.005",
            },
            {
              model_id: MODEL_SMALL,
              purpose: "chat",
              trigger: "user",
              calls: 1,
              input_tokens: 1000,
              output_tokens: 100,
              cost_usd: "0.001",
            },
          ],
        }),
      ),
    );
    renderWithClient(<UsageSection />);
    const table = await screen.findByRole("table", { name: "By purpose" });
    expect(within(table).getByText("agent run")).toBeInTheDocument();
    expect(within(table).getByText("chat")).toBeInTheDocument();
  });
});
