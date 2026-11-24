// Scans the built page after `vite build`. It fails the build when the output would load or
// link anything the landing page must not: a remote resource, an unknown external link, or a
// missing Content-Security-Policy.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const DIST = fileURLToPath(new URL("../dist/", import.meta.url));

// External addresses the built files may contain. Anything else fails the build.
export const ALLOWED = [
  "https://github.com/MohammadAnas-07/MantleAI", // the only outbound link on the page
  "http://www.w3.org/", // XML namespaces inside SVG, never fetched
  "https://react.dev/errors/", // React's production error messages, never fetched
  "https://tailwindcss.com", // the licence comment at the top of the CSS, never fetched
  "http://127.0.0.1:", // the local addresses printed in the setup instructions
];

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

const problems = [];
for (const path of files(DIST)) {
  if (!/\.(html|js|css|svg)$/.test(path)) continue;
  const text = readFileSync(path, "utf-8");
  for (const [url] of text.matchAll(/https?:\/\/[^\s"'`)<>\\]+/g)) {
    if (!ALLOWED.some((allowed) => url.startsWith(allowed))) problems.push(`${path}: ${url}`);
  }
  if (/url\(\s*["']?data:/.test(text)) problems.push(`${path}: a data: URL in CSS`);
}

const html = readFileSync(join(DIST, "index.html"), "utf-8");
if (!html.includes('http-equiv="Content-Security-Policy"')) problems.push("index.html: no CSP");
if (/<(script|link|img|iframe)[^>]+(src|href)="https?:/i.test(html)) {
  problems.push("index.html: a remote script, stylesheet, image or frame");
}

if (problems.length > 0) {
  console.error("The built landing page breaks its rules:");
  for (const p of problems) console.error(`  ${p}`);
  process.exit(1);
}
console.warn("Built page checked: CSP present, no remote resources, only allowed links.");
