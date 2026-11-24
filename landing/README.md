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

## Host it on GitHub Pages

The build uses relative paths (`base: "./"` in `vite.config.ts`), so `dist/` works at the site
root and under a sub-path such as `https://<user>.github.io/MantleAI/`. To publish by hand:

1. `npm run build`.
2. Publish the contents of `dist/` to the branch or folder that GitHub Pages serves (repository
   Settings, then Pages).
3. Open the page and check that the CSS loads and the Copy buttons work. The clipboard needs
   HTTPS, which GitHub Pages provides.

There is no deploy workflow yet; CI only builds and checks the page.
