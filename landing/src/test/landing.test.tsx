import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { BACKEND_COMMANDS, FRONTEND_COMMANDS, NAV, REPO } from "../content";
import { contentSecurityPolicy, injectCsp } from "../csp";
import { SCREENSHOTS } from "../screenshots";

describe("page structure", () => {
  it("renders every section the nav names, with a heading each", () => {
    const { container } = render(<App />);
    for (const id of [...NAV.map((n) => n.id), "problem", "numbers", "faq"]) {
      const section = container.querySelector(`section#${id}`);
      expect(section, id).not.toBeNull();
      expect(within(section as HTMLElement).getAllByRole("heading").length).toBeGreaterThan(0);
    }
    expect(screen.getByRole("contentinfo")).toHaveTextContent("One developer builds Mantle.");
  });

  it("has exactly one h1 and never skips a heading level", () => {
    const { container } = render(<App />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    const levels = [...container.querySelectorAll("h1, h2, h3, h4, h5, h6")].map((h) =>
      Number(h.tagName[1]),
    );
    expect(levels[0]).toBe(1);
    levels.forEach((level, i) => {
      if (i > 0) expect(level - (levels[i - 1] ?? 1), `heading ${i}`).toBeLessThanOrEqual(1);
    });
  });

  it("links only to sections that exist and to the GitHub repository", () => {
    const { container } = render(<App />);
    const hrefs = [...container.querySelectorAll("a")].map((a) => a.getAttribute("href") ?? "");
    expect(hrefs.length).toBeGreaterThan(10);
    for (const href of hrefs) {
      if (href.startsWith("#")) {
        expect(container.querySelector(href), href).not.toBeNull();
      } else {
        expect(href.startsWith(REPO), href).toBe(true);
      }
    }
  });

  it("gives every image and the diagram a text alternative", () => {
    const { container } = render(<App />);
    for (const img of container.querySelectorAll("img")) {
      expect(img.getAttribute("alt")?.trim()).toBeTruthy();
    }
    expect(screen.getByRole("img", { name: /How Mantle builds a prompt/ })).toBeInTheDocument();
  });

  it("starts with a skip link to the main content", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.tab();
    const skip = screen.getByRole("link", { name: "Skip to content" });
    expect(skip).toHaveFocus();
    expect(skip).toHaveAttribute("href", "#main");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
  });

  it("claims no more than the README about providers and readiness", () => {
    const { container } = render(<App />);
    const text = container.textContent;
    expect(text).toMatch(/real runs used only Gemini/);
    expect(text).toMatch(/Real runs: Gemini only/);
    expect(text).toMatch(/Open source · MIT licence · Runs on your machine/);
    expect(text).not.toMatch(/any provider/i);
    expect(text).not.toMatch(/production[- ]ready/i);
  });

  it("keeps the safety notes on the page, with a link to the other known issues", () => {
    render(<App />);
    const section = document.getElementById("what-works") as HTMLElement;
    const list = within(section).getByRole("heading", { name: "Before you run it" })
      .nextElementSibling as HTMLElement;
    const items = within(list)
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    expect(items).toHaveLength(5);
    expect(items.join(" ")).toMatch(/no login/i);
    expect(items.join(" ")).toMatch(/sends your code to your embedding provider/);
    expect(items.join(" ")).toMatch(/only on Gemini/);
    expect(items.join(" ")).toMatch(/restart stops them/);
    expect(items.join(" ")).toMatch(/no automatic backup/);
    expect(
      within(section).getByRole("link", { name: "More known issues on GitHub" }),
    ).toBeInTheDocument();
  });
});

describe("mobile menu", () => {
  it("opens and closes by keyboard and gives focus back", async () => {
    const user = userEvent.setup();
    render(<App />);
    const button = screen.getByRole("button", { name: "Menu" });
    expect(button).toHaveAttribute("aria-expanded", "false");

    button.focus();
    await user.keyboard("{Enter}");
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button).toHaveTextContent("Close menu");
    const menu = screen.getByRole("navigation", { name: "Menu" });
    expect(
      within(menu)
        .getAllByRole("link")
        .map((a) => a.textContent),
    ).toEqual([...NAV.map((n) => n.label), "GitHub"]);

    await user.tab();
    expect(within(menu).getAllByRole("link")[0]).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("navigation", { name: "Menu" })).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  it("closes when a section is chosen", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Menu" }));
    const menu = screen.getByRole("navigation", { name: "Menu" });
    await user.click(within(menu).getByRole("link", { name: "Setup" }));
    expect(screen.queryByRole("navigation", { name: "Menu" })).not.toBeInTheDocument();
  });
});

describe("copy buttons", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("copy exactly the command shown and announce it", async () => {
    vi.useFakeTimers();
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<App />);

    const backend = screen.getByRole("button", { name: "Copy: 1. Database and API" });
    await act(async () => {
      fireEvent.click(backend);
      await Promise.resolve();
    });
    expect(writeText).toHaveBeenLastCalledWith(BACKEND_COMMANDS);
    expect(screen.getByText("Copied to the clipboard.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copied: 1. Database and API" })).toBeVisible();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Copy: 2\. Web app/ }));
      await Promise.resolve();
    });
    expect(writeText).toHaveBeenLastCalledWith(FRONTEND_COMMANDS);

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByRole("button", { name: "Copy: 1. Database and API" })).toBeVisible();
  });

  it("says so when the clipboard refuses", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: () => Promise.reject(new Error("denied")) },
      configurable: true,
    });
    render(<App />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copy: 1. Database and API" }));
      await Promise.resolve();
    });
    expect(screen.getByText(/Copy failed\. Select the text/)).toBeInTheDocument();
  });

  it("show the Windows path with its backslashes", () => {
    render(<App />);
    expect(screen.getByText(/\.venv\\Scripts\\Activate\.ps1/)).toBeInTheDocument();
  });
});

describe("content security policy", () => {
  it("allows only the page's own origin and no connections", () => {
    const policy = contentSecurityPolicy();
    expect(policy).toContain("default-src 'self';");
    expect(policy).toContain("connect-src 'none';");
    expect(policy).toContain("frame-src 'none';");
    expect(policy).not.toContain("unsafe-inline");
    expect(policy).not.toContain("data:");
    expect(policy).not.toMatch(/https?:/);
  });

  it("is the first element of <head>", () => {
    const html = injectCsp("<html><head><title>x</title></head></html>");
    expect(html).toMatch(/^<html><head><meta http-equiv="Content-Security-Policy"/);
  });
});

describe("screenshots", () => {
  // The empty-folder case (no figure at all) is covered in screenshots-plugin.test.ts.
  it("shows every screenshot found, with alt text and a fixed size", () => {
    const { container } = render(<App />);
    const imgs = [...container.querySelectorAll("img")];
    expect(imgs).toHaveLength(SCREENSHOTS.length);
    for (const img of imgs) {
      expect(img.getAttribute("alt")?.trim()).toBeTruthy();
      expect(Number(img.getAttribute("width"))).toBeGreaterThan(0);
      expect(Number(img.getAttribute("height"))).toBeGreaterThan(0);
    }
  });
});
