---
version: 2
name: Mantle landing page
description: The public page in landing/. It uses the app's tokens from docs/design-app.md so the page and the app read as one product, plus the few extras a long scrolling page needs - ink bands, a charcoal tile, a frosted header and display serif sizes. Editorial and quiet - ink on white, warm greys, hairlines, one blue accent, almost no motion.
colors:
  paper: "#FFFFFF"      # canvas, light bands
  linen: "#F7F6F4"      # alternate bands, code on paper (app "sunken")
  hover: "#EFEDE9"      # hovered nav links and outline buttons on paper
  rule: "#E4E1DC"       # hairlines (decorative only)
  field: "#8A857D"      # control edges: outline buttons, the menu button
  ink: "#1C1A17"        # text, the solid primary button, dark bands
  ink-2: "#3A3732"      # secondary text, primary button hover
  muted: "#6B675F"      # captions, eyebrows on paper
  accent: "#1D5FB4"     # links and the focus ring on paper (one accent, used sparingly)
  on-ink: "#FFFFFF"     # text on ink and charcoal
  charcoal: "#2A2724"   # code blocks and tiles inside ink bands
  pebble: "#A6A199"     # captions and legal text on ink
  accent-on-ink: "#7FB0EF"  # links and the focus ring on ink bands
  ink-rule: "#4A4741"   # hairlines on ink (decorative)
typography:
  serif: '"Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif'
  sans: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
  mono: 'ui-monospace, "Cascadia Mono", Consolas, Menlo, monospace'
  scale:
    hero:      { size: "clamp(40px, 7vw, 72px)", line: 1.05, tracking: "-0.0125em", family: serif }
    display:   { size: "clamp(32px, 4.5vw, 48px)", line: 1.05, tracking: "-0.01em", family: serif }
    display-sm: { size: "clamp(24px, 3vw, 32px)", line: 1.1, tracking: "-0.01em", family: serif }
    title:     { size: 20px, line: 1.3, weight: 500, family: sans }
    lead:      { size: 20px, line: 1.4, family: sans }
    body:      { size: 16px, line: 1.5, family: sans }
    label:     { size: 14px, line: 1.3, weight: 500, family: sans }
    caption:   { size: 14px, line: 1.4, family: sans }
    code:      { size: 14px, line: 1.6, family: mono }
  weights: [400, 500]
spacing:
  base: 8px
  band-y: 64px (96px for the hero, 48px under 768px)
  container: 1200px
  measure: 68ch
  gutter: "24px (16px under 768px)"
rounded: { control: 4px, container: 8px }
elevation:
  header: "rgb(255 255 255 / 0.85) with backdrop-filter blur(16px), hairline below"
  overlay: "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)"  # the open mobile menu only
---

# Mantle landing page design

Scope: `landing/` only. The app keeps `docs/design-app.md`. Both share the same ink, greys,
accent and font stacks; the landing page adds display sizes, bands and a dark footer.

## Principles

- Three moves make hierarchy: serif for statements, a jump in size, and a band that flips to
  ink. Nothing else: no gradients, no shadows on content, no second hue.
- One headline owns a band. Text blocks stay under 68 characters wide.
- Every claim on the page comes from the README, the docs or the measured-numbers file. Planned
  work says "planned". Limits are on the page, not hidden.
- Honest visuals only: diagrams drawn in SVG or CSS. No fake screenshots, logos or quotes.

## Contrast (WCAG 2.1)

| Pair | Ratio | Use |
| --- | --- | --- |
| ink on paper / linen / hover | 17.36 / 16.08 / 14.85 | text |
| ink-2 on paper / linen | 11.85 / 10.97 | secondary text |
| muted on paper / linen | 5.63 / 5.21 | captions, eyebrows |
| accent on paper / linen | 6.27 / 5.81 | links, focus ring |
| on-ink on ink | 17.36 | footer, primary button |
| on-ink on ink-2 | 11.85 | primary button hover |
| on-ink on charcoal | 14.85 | code on ink |
| code text #E9E6E1 on charcoal | 11.93 | code blocks |
| pebble on ink / charcoal | 6.76 / 5.78 | legal text, captions on ink |
| accent-on-ink on ink / charcoal | 7.74 / 6.62 | links and focus on ink |
| field on paper | 3.66 | control edges (3:1 needed) |
| rule, ink-rule | 1.3, 1.9 | decorative hairlines only, never the only edge of a control |

## Layout and bands

- Container 1200px with 24px gutters (16px under 768px). A 12-column grid only where two
  things sit side by side (hero text and diagram, setup steps and code).
- Bands, top to bottom: hero (paper), problem (linen), how it works (paper), what it does
  (linen), privacy (paper), setup (linen), status (paper), numbers (linen), FAQ (paper),
  footer (ink). A band change is the only section divider.
- Band padding 64px top and bottom; hero 96px; 48px under 768px.
- Each band starts with an eyebrow (label, muted) and a display serif title, then at most one
  lead line.

## Header (navigation)

- Sticky, 72px (64px under 768px), full-bleed, frosted: paper at 85% with a 16px backdrop blur
  and a hairline below. Never opaque.
- Left: the wordmark "Mantle" in serif 22px, linking to the top. Middle: text links in label
  style, 4px apart, each with a 44px hit area. Right: one outline "GitHub" button.
- Current section: ink text with a 2px accent underline, set with `aria-current="true"` when
  the section is in view. Other links are ink-2; hover turns them ink with the underline in rule.
- Skip link: the first focusable element, hidden until focused, then a paper box top left.
- Under 900px the links fold into a "Menu" button (44px, field outline). Open: a full-width
  paper panel under the header with the overlay shadow, links stacked as 48px rows split by
  hairlines. The button says "Close menu" and has `aria-expanded`. Escape closes and returns
  focus to the button; choosing a link closes it.

## Hero

- Left: eyebrow "Open source · MIT licence", the hero serif headline (two lines at most), one
  lead sentence, two buttons (solid "View on GitHub", outline "Quick start"), and a caption
  line: open source, MIT licence, runs on your machine.
- Right: the flow diagram in SVG (project data and a model on each side of the context
  builder, a model switch arrow). It has a `<title>` and a text description; it carries no
  information that the text does not also give.
- Under 900px the diagram moves below the text.

## Buttons and links

- Primary: ink fill, on-ink text, 48px high, 20px side padding, 4px radius. Hover ink-2.
  Pressed: ink-2 with the label moved 1px down (no movement with reduced motion).
- Outline: 1px ink border, ink text, same size. Hover and pressed: ink fill, on-ink text.
- On ink bands the outline button uses an on-ink border and text; hover fills on-ink with ink
  text.
- Text links: accent on paper, accent-on-ink on ink, underlined, 2px offset. External links
  name their target ("on GitHub") and never open a new window.

## Code block

- Charcoal fill, code text #E9E6E1, mono 14px, 4px radius, 16px padding, scrolls sideways,
  `dir="ltr"`. A "Copy" button sits top right: 44px hit area, label text. After copying it
  says "Copied" for 2 seconds and a polite live region says "Copied to the clipboard". If the
  clipboard is not available it says "Copy failed" and the text stays selectable.
- A shell comment in the code (`# ...`) is muted but passes AA (pebble on charcoal, 5.78).

## Table

- Full width, 16px text, rows split by hairlines, a header row in label style (muted). On
  small screens the table scrolls inside its own box; the page never scrolls sideways.

## Lists, steps and status

- Steps: a serif numeral (display-sm, muted) left of a title and one sentence, rows split by
  hairlines.
- Feature list: two columns on desktop, one on mobile; each item is a title (sans 500) and one
  concrete line.
- Status columns: "Works today", "Planned, not built" and "Known limits". Each item starts with
  a word, not a colour. The limits column has the same weight as the others.

## Footer

- Ink band. A serif statement (display-sm), then link columns (Project, Setup, Legal) in label
  style with 16px gaps, two columns under 768px. An ink-rule hairline, then the legal line in
  pebble caption: who builds it and the licence.
- No newsletter, no social icons.

## Motion and states

- Motion: colour and background transitions of 150ms ease-out on links and buttons. Smooth
  scroll to anchors. With `prefers-reduced-motion` there is no transition and no smooth
  scroll.
- Hover: described per component above. Pressed: as hover, plus the 1px label shift on the
  primary button. Focus: a 2px accent ring with a 2px paper gap (accent-on-ink on ink bands),
  drawn with `outline`, never removed.
- Menu open: see header. Copy states: see code block.

## Responsive

- 1200px and up: full layout. 900 to 1199px: the same, with tighter gaps.
- 768 to 899px (tablet): navigation in the menu; hero text above the diagram; two-column lists
  stay two columns.
- Under 768px: one column everywhere, footer links in two columns, bands at 48px, display
  sizes from their clamp minimums. Works without horizontal scroll from 360px.
- Touch targets at least 44px on every link and button.

## Assets and privacy

- System font stacks only: no webfont, no font request.
- No remote images, scripts, iframes, analytics or cookies. The only external links are plain
  links to the GitHub repository.
- A strict Content-Security-Policy meta tag: everything from `'self'`, no `connect-src` beyond
  it, no frames, no objects.
- Favicon: an original SVG (a serif "M" on ink).
- Screenshots appear only if real PNG or WebP files exist in `landing/public/screenshots/`,
  each with alt text that says what the screen shows. No placeholder boxes.
