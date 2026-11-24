// The Content-Security-Policy of the built page (vite.config.ts adds it to index.html).
//
// The page is static: no API, no analytics, no remote fonts, images or scripts. Everything it
// needs comes from its own origin, and it may not connect anywhere. The dev server doesn't get
// this policy, because Vite's hot reload needs inline scripts.

export function contentSecurityPolicy(): string {
  const directives: [string, string][] = [
    ["default-src", "'self'"],
    ["script-src", "'self'"],
    ["style-src", "'self'"],
    ["img-src", "'self'"],
    ["font-src", "'self'"],
    ["connect-src", "'none'"],
    ["frame-src", "'none'"],
    ["object-src", "'none'"],
    ["base-uri", "'self'"],
    ["form-action", "'none'"],
  ];
  return directives.map(([name, value]) => `${name} ${value};`).join(" ");
}

/** index.html with the policy as the first element of <head>. */
export function injectCsp(html: string): string {
  if (!html.includes("<head>")) throw new Error("index.html has no <head>: can't add the CSP.");
  const tag = `<meta http-equiv="Content-Security-Policy" content="${contentSecurityPolicy()}" />`;
  return html.replace("<head>", `<head>${tag}`);
}
