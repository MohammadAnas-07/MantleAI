import { describe, expect, it } from "vitest";

import { contentSecurityPolicy, cspMetaTag, injectCsp } from "./csp";

function directives(policy: string): Map<string, string[]> {
  return new Map(
    policy
      .split(";")
      .map((d) => d.trim().split(/\s+/))
      .filter((parts) => parts[0])
      .map(([name = "", ...values]) => [name, values]),
  );
}

describe("Content-Security-Policy", () => {
  const policy = directives(contentSecurityPolicy("http://127.0.0.1:8000"));

  it("blocks remote images, scripts, frames and plugins", () => {
    expect(policy.get("default-src")).toEqual(["'self'"]);
    expect(policy.get("img-src")).toEqual(["'self'"]);
    expect(policy.get("script-src")).toEqual(["'self'"]);
    expect(policy.get("frame-src")).toEqual(["'none'"]);
    expect(policy.get("object-src")).toEqual(["'none'"]);
    expect(policy.get("base-uri")).toEqual(["'self'"]);
    expect(policy.get("form-action")).toEqual(["'self'"]);
  });

  it("lets the app talk only to itself and the Mantle API", () => {
    expect(policy.get("connect-src")).toEqual(["'self'", "http://127.0.0.1:8000"]);
  });

  it("uses the API origin only, never a path, and refuses a bad URL", () => {
    expect(contentSecurityPolicy("http://localhost:8000/some/path")).toContain(
      "connect-src 'self' http://localhost:8000;",
    );
    expect(() => contentSecurityPolicy("not a url")).toThrow();
  });

  it("is added to the built index.html as the first thing in <head>", () => {
    const html = injectCsp(
      "<!doctype html><html><head><title>Mantle</title></head></html>",
      "http://127.0.0.1:8000",
    );
    expect(html).toContain(`<head>${cspMetaTag("http://127.0.0.1:8000")}<title>`);
    expect(html.match(/Content-Security-Policy/g)).toHaveLength(1);
  });
});
