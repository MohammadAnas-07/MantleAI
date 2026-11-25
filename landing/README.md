# Mantle landing page

The public page for Mantle: one static page with no API calls, analytics, cookies or remote
resources. Design: `../docs/design-landing.md`. All text is in `src/content.ts`, each block with
the document it comes from.

## Run it

Node.js 22 or newer. From this folder:

```powershell
npm install
npm run dev          # http://127.0.0.1:5174 (the app's dev server keeps 5173)
```

## Checks

```powershell
npm run typecheck; npm run lint; npm run format:check; npm run test; npm run build
```

`npm run build` writes `dist/` and then runs `scripts/check-dist.mjs`. The build fails if the
output has no Content-Security-Policy, loads a remote resource, or contains an external address
that is not on the short allow-list in that script (the GitHub repository and a few addresses
that are never fetched).

## Preview the built page

```powershell
npm run build
npm run preview      # http://127.0.0.1:5174, the files in dist/ with the CSP
```

The CSP is added only to the built page. The dev server runs without it, because Vite's hot
reload needs inline scripts.

## Screenshots

Put real PNG or WebP files in `public/screenshots/`. The build finds them, reads their size so
the page doesn't jump, and shows them under the feature list. Alt text comes from
`public/screenshots/alt.json`, for example `{ "chat.png": "A conversation with cited code" }`,
or from the file name. With no files, the page shows no figure at all.

## Hosting on GitHub Pages

Live at <https://mohammadanas-07.github.io/MantleAI/>.

`.github/workflows/pages.yml` builds this folder with `npm run build` (output scan included) and
deploys `dist/` to GitHub Pages. It runs on every push to `main` that changes `landing/` or the
workflow, and by hand from the Actions tab ("Landing page", then "Run workflow").

One-time setup in the repository: Settings, then Pages, then Source: "GitHub Actions".

The build uses relative paths (`base: "./"` in `vite.config.ts`), so `dist/` works under the
`/MantleAI/` sub-path as well as at a site root. After a deploy, open the page and check that
the CSS loads and the Copy buttons work (the clipboard needs HTTPS, which Pages provides).
