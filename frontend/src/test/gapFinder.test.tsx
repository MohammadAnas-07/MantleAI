import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { API, apiError, MODEL_SMALL, PROJECT_ID } from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";
import { agentRun, DECISION_ID, memoryItem, REQ_ID } from "./workflowFixtures";

const GAP = `${API}/api/v1/projects/${PROJECT_ID}/gap-finder`;
const PAGE = `/projects/${PROJECT_ID}/workflow`;

const gapRun = (id: string, extra = {}) =>
  agentRun("completed", {
    id,
    run_type: "gap_finder",
    cost_usd: "0.0021",
    result: {
      missing_steps: [
        {
          title: "No password reset",
          explanation: "Users can't recover accounts.",
          severity: "high",
          refers_to: [REQ_ID],
        },
      ],
      risks: [
        {
          title: "<img src=x onerror=alert(1)>",
          explanation: "**not bold**",
          severity: "medium",
          refers_to: [DECISION_ID],
        },
      ],
      technical_debt: [],
      scalability_concerns: [],
    },
    warnings: [{ code: "unknown_reference", where: "risks", reference: "zzzz" }],
    ...extra,
  });

function withMemory() {
  server.use(
    http.get(`${API}/api/v1/projects/${PROJECT_ID}/memory`, ({ request }) => {
      const kind = new URL(request.url).searchParams.get("kind");
      const items =
        kind === "requirement"
          ? [memoryItem(REQ_ID, "requirement", "Users can log in")]
          : kind === "decision"
            ? [memoryItem(DECISION_ID, "decision", "Use argon2")]
            : [];
      return HttpResponse.json({ items, total: items.length, limit: 100, offset: 0 });
    }),
  );
}

describe("gap finder", () => {
  it("groups findings with severity, links references and shows warnings", async () => {
    withMemory();
    server.use(http.get(GAP, () => HttpResponse.json({ items: [gapRun("g1")] })));
    renderApp(PAGE);
    const result = await screen.findByRole("article", { name: "Gap finder result" });
    const missing = within(result).getByRole("region", { name: "Missing steps" });
    expect(within(missing).getByText("No password reset")).toBeInTheDocument();
    expect(within(missing).getByText("high severity")).toBeInTheDocument();
    const link = await within(missing).findByRole("link", {
      name: "requirement: Users can log in",
    });
    expect(link).toHaveAttribute("href", `/projects/${PROJECT_ID}/memory/${REQ_ID}`);
    expect(within(result).getByRole("region", { name: "Technical debt" })).toHaveTextContent(
      "None found.",
    );
    // Model text is shown as plain text: no HTML element, no Markdown.
    const risks = within(result).getByRole("region", { name: "Risks" });
    expect(within(risks).getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(within(risks).getByText("**not bold**")).toBeInTheDocument();
    expect(result.querySelector("img")).toBeNull();
    const warnings = within(result).getByRole("list", { name: "Warnings" });
    expect(warnings).toHaveTextContent(/A reference in risks to an item the project doesn't have/);
    expect(warnings).not.toHaveTextContent("zzzz");
  });

  it("says it costs money and asks before forcing past the cost limit", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(GAP, async ({ request }) => {
        const body = (await request.json()) as { force: boolean };
        bodies.push(body);
        if (!body.force) {
          return HttpResponse.json(
            apiError("cost_limit_exceeded", "Over the limit.", {
              estimate: {
                steps: 1,
                input_tokens: 90_000,
                output_tokens: 8_000,
                cost_usd: "0.72",
                cost_limit_usd: "0.50",
                model: "google/Small Model",
              },
            }),
            { status: 409 },
          );
        }
        return HttpResponse.json(gapRun("g2"));
      }),
    );
    const { user } = renderApp(PAGE);
    expect(await screen.findByText(/Your provider bills you for it/)).toBeInTheDocument();
    const find = screen.getByRole("button", { name: "Find gaps" });
    await waitFor(() => {
      expect(find).toBeEnabled();
    });
    await user.click(find);
    const dialog = await screen.findByRole("dialog", { name: "Run above the cost limit?" });
    expect(dialog).toHaveTextContent("$0.72");
    expect(dialog).toHaveTextContent("$0.50");
    await user.click(within(dialog).getByRole("button", { name: "Run anyway" }));
    await waitFor(() => {
      expect(bodies).toEqual([
        { model_id: MODEL_SMALL, force: false },
        { model_id: MODEL_SMALL, force: true },
      ]);
    });
  });

  it("explains an unpriced model and a provider failure without provider text", async () => {
    let calls = 0;
    server.use(
      http.post(GAP, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(apiError("model_not_priced", "x has no price."), { status: 422 })
          : HttpResponse.json(
              apiError("provider_unavailable", "upstream said: secret prompt text", {
                run_id: "g3",
              }),
              { status: 503 },
            );
      }),
    );
    const { user } = renderApp(PAGE);
    const find = await screen.findByRole("button", { name: "Find gaps" });
    await waitFor(() => {
      expect(find).toBeEnabled();
    });
    await user.click(find);
    expect(await screen.findByText(/cost limit can't be applied/)).toBeInTheDocument();
    await user.click(find);
    expect(await screen.findByText(/did not answer.*Try again later/)).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("secret prompt text");
  });

  it("lists past results and shows the one picked", async () => {
    server.use(
      http.get(GAP, () =>
        HttpResponse.json({
          items: [
            gapRun("new", { created_at: "2026-11-20T12:00:00Z" }),
            agentRun("failed", {
              id: "old",
              run_type: "gap_finder",
              error: "invalid_output",
              error_message: "The JSON doesn't match the schema: risks: Field required",
              created_at: "2026-11-19T12:00:00Z",
            }),
          ],
        }),
      ),
    );
    const { user } = renderApp(PAGE);
    const past = await screen.findByRole("heading", { name: "Past results" });
    const list = past.nextElementSibling as HTMLElement;
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    await user.click(within(list).getAllByRole("button")[1] as HTMLElement);
    expect(
      await screen.findByText(/also after one retry.*risks: Field required/),
    ).toBeInTheDocument();
  });
});
