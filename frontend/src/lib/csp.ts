// The Content-Security-Policy of the built app (vite.config.ts adds it to index.html).
//
// Model output, memory and retrieved code are shown in the page. Even if something slipped past
// the renderers, the browser must not load a remote image, script, frame or plugin from it, and
// the page may only talk to itself and the Mantle API. The dev server doesn't get this policy:
// Vite's hot reload needs inline scripts. `npm run build` and `npm run preview` do.

/** The policy for an app whose API is at `apiBaseUrl` (only its origin is used). */
export function contentSecurityPolicy(apiBaseUrl: string): string {
  const api = new URL(apiBaseUrl).origin; // throws on a bad URL: fail the build, not the page
  const directives: [string, string][] = [
    ["default-src", "'self'"],
    ["script-src", "'self'"],
    // Tailwind ships a stylesheet, but React sets a few inline style attributes (widths).
    ["style-src", "'self' 'unsafe-inline'"],
    // data: covers the inline SVG noise texture; nothing remote.
    ["img-src", "'self' data:"],
    ["font-src", "'self'"],
    ["connect-src", `'self' ${api}`],
    ["frame-src", "'none'"],
    ["object-src", "'none'"],
    ["base-uri", "'self'"],
    ["form-action", "'self'"],
  ];
  return directives.map(([name, value]) => `${name} ${value};`).join(" ");
}

export function cspMetaTag(apiBaseUrl: string): string {
  return `<meta http-equiv="Content-Security-Policy" content="${contentSecurityPolicy(apiBaseUrl)}" />`;
}

/** index.html with the policy as the first element of <head>. */
export function injectCsp(html: string, apiBaseUrl: string): string {
  if (!html.includes("<head>")) throw new Error("index.html has no <head>: can't add the CSP.");
  return html.replace("<head>", `<head>${cspMetaTag(apiBaseUrl)}`);
}
