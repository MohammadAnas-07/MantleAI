---
version: 2
name: Mantle app
description: The look of the Mantle web app in frontend/. Warm near-black ink on white, a short ladder of warm stone greys, hairline rules instead of boxes, small corners, a serif for page titles only and a compact system sans for everything else. One restrained blue for links, selection and focus. Status colours exist only next to a word or an icon.
colors:
  light:
    paper: "#FFFFFF"        # main area, panels, inputs, dialogs
    sunken: "#F7F6F4"       # sidebar, table heads, code blocks, user messages
    hover: "#EFEDE9"        # row and ghost button hover, selected nav item
    hairline: "#E4E1DC"     # dividers between rows and columns (decorative, not a control edge)
    field: "#8A857D"        # control borders: inputs, selects, checkboxes, outline buttons
    ink: "#1C1A17"          # body text, headings, primary button fill
    ink-2: "#3A3732"        # secondary prose
    muted: "#6B675F"        # meta text, captions, placeholders
    accent: "#1D5FB4"       # links, focus ring, selected tab, selected checkbox
    accent-soft: "#EEF3FA"  # info banner and badge fill
    success: "#1F6B3A"
    success-soft: "#EDF5EF"
    warning: "#8A5300"
    warning-soft: "#FBF3E2"
    danger: "#A8321F"
    danger-soft: "#FBEDEA"
    on-ink: "#FFFFFF"
    on-danger: "#FFFFFF"
  dark:
    paper: "#1E1C1A"
    sunken: "#161513"
    hover: "#282624"
    hairline: "#34312D"
    field: "#77726B"
    ink: "#ECE9E4"
    ink-2: "#D3CFC8"
    muted: "#A6A199"
    accent: "#7FB0EF"
    accent-soft: "#1B2533"
    success: "#7FC493"
    success-soft: "#1F2B22"
    warning: "#E3B25C"
    warning-soft: "#2E2616"
    danger: "#F0907E"
    danger-soft: "#33201C"
    on-ink: "#161513"
    on-danger: "#161513"
typography:
  serif: '"Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif'
  sans: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
  mono: 'ui-monospace, "Cascadia Mono", Consolas, Menlo, "DejaVu Sans Mono", monospace'
  scale:
    xs:    { size: 12px, line: 16px }   # badges, table heads, hints
    sm:    { size: 13px, line: 18px }   # meta, help text, secondary rows
    base:  { size: 14px, line: 20px }   # the UI default: buttons, inputs, rows, panels
    md:    { size: 15px, line: 24px }   # chat messages and long prose
    lg:    { size: 16px, line: 22px }   # section headings (sans 500)
    xl:    { size: 20px, line: 26px }   # dialog titles (sans 500)
    title: { size: 28px, line: 32px, tracking: -0.28px }  # page titles (serif 400)
  weights: [400, 500]
spacing: [0, 4, 8, 12, 16, 24, 32, 48]
rounded:
  sm: 4px    # every control, badge, nav item, message
  lg: 8px    # dialogs, cards, code blocks, empty states
elevation:
  overlay: "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)"  # dialogs only
motion:
  duration: 150ms
  easing: ease-out
  properties: [color, background-color, border-color]
---

# Mantle app design

This file replaces the "grunge-lite" design. It covers the app only. The landing page keeps
`docs/design-landing.md`, and nothing here applies to it.

## Overview

Mantle is a working tool. People read model output, compare numbers and approve plans in it for
hours. The design gets out of the way:

- Ink on paper, with greys for structure. Colour means status or "you can click this", nothing
  else.
- Rows and columns are split by hairlines. Boxes are rare: dialogs, code, a run in progress, a
  plan item you are editing.
- A serif sets the page title, once per page. Everything else is the system sans at 13 to 15px.
- Two weights: 400 and 500. Emphasis comes from size, position or the serif, not from bold.
  The one exception is `**bold**` in model output, which renders at 600 so the model's emphasis
  survives.
- Density is medium: 32px rows and controls, 16px gutters, 24px between sections.

## Colors

Tokens live in `frontend/src/index.css` as CSS variables, mapped to Tailwind colours in
`@theme`. Components use the Tailwind names (`bg-paper`, `text-muted`, `border-line`), never a
hex value.

| Tailwind name | Token | Use |
| --- | --- | --- |
| `paper` | paper | main area, right panel, inputs, dialogs |
| `sunken` | sunken | sidebar, top bar, table heads, code, user messages |
| `hover` | hover | hovered rows and ghost buttons, the selected nav item |
| `line` | hairline | dividers |
| `field` | field | control borders (3.66:1 on paper, passes 3:1 for UI parts) |
| `text`, `text-2`, `muted` | ink, ink-2, muted | text ladder |
| `accent`, `accent-soft` | accent | links, focus, selected tab, info |
| `success`, `warning`, `danger` (+ `-soft`) | | status text, icons and soft fills |
| `primary`, `on-primary` | ink, on-ink | the primary button |
| `danger-strong`, `on-danger` | danger, on-danger | the danger button |

Rules:
- One primary button per view. Everything else is secondary (outline) or ghost.
- Soft status fills hold status text in the matching strong colour (all pairs pass AA, see the
  table below). Never put status colour on paper without a word or an icon.
- The hairline is decorative (1.3:1). A control edge always uses `field`.
- The light theme is the default. The dark theme stays because the app had one; the toggle is in
  the top bar and the choice is kept in `localStorage` (the only thing stored there).

### Contrast (WCAG 2.1, checked with a script)

| Pair | Light | Dark |
| --- | --- | --- |
| ink on paper / sunken / hover | 17.36 / 16.08 / 14.85 | 14.03 / 15.07 / 12.45 |
| ink-2 on paper | 11.85 | 10.94 |
| ink on accent-soft / warning-soft / danger-soft (banner text) | 15.57 / 15.73 / 15.22 | 12.76 / 12.34 / 12.71 |
| muted on paper / sunken / hover | 5.63 / 5.21 / 4.81 | 6.62 / 7.11 / 5.87 |
| accent on paper / sunken / accent-soft | 6.27 / 5.81 / 5.63 | 7.57 / 8.13 / 6.89 |
| on-ink on ink (primary button) | 17.36 | 15.07 |
| success on paper / success-soft | 6.52 / 5.87 | 8.27 / 7.16 |
| warning on paper / warning-soft | 6.33 / 5.73 | 8.73 / 7.68 |
| danger on paper / danger-soft | 6.69 / 5.86 | 7.28 / 6.59 |
| on-danger on danger (danger button) | 6.69 | 7.82 |
| field (control edge) on paper / sunken | 3.66 / 3.39 | 3.56 / 3.83 |

## Typography

- Page titles (`h1`): serif 400, 28px, tracking -0.28px, `font-serif text-title`. One per page.
- Section headings (`h2`): sans 500, 16px. Sub-headings (`h3`, `h4`): sans 500, 14px.
- Dialog titles: sans 500, 20px.
- UI text: sans 400, 14px/20px. Meta and help: 13px, `muted`.
- Chat and long prose: 15px/24px, at most 72 characters per line.
- Code, paths, ids and token counts in tables: mono, 13px. Numbers in tables are
  `tabular-nums` and right-aligned.
- Eyebrow labels (table heads, field group captions): 12px, 500, `muted`. No uppercase, no
  letter spacing.
- No webfont: all three stacks are system fonts, so the build makes no font request.

## Layout

```
+--------------------------------------------------------------------------+
| Mantle   Project › Conversation            [Model v]  [theme] [settings] |  top bar, 48px
+--------------+-------------------------------------------+---------------+
| Explorer     | page title (serif)                        | AI panel      |
|  Projects    |                                           | Memory Index  |
|  > Demo      | content                                   | Profile Ctx   |
|    Overview  |                                           |               |
|    Workflow  |                                           |               |
|  Conversat.  |                                           |               |
+--------------+-------------------------------------------+---------------+
| Activity (collapsed bar)                                                 |
+--------------------------------------------------------------------------+
```

- Columns touch and are split by a hairline; no gaps, no panel boxes.
- The sidebar is `sunken`, the main area and right panel are `paper`.
- Side panels can be collapsed (button in the panel header, `aria-expanded`) and resized with a
  keyboard handle (arrow keys, Shift for bigger steps).
- The main area has 24px padding (16px under 1024px). Prose and forms keep to about 720px.
- Under 768px everything stacks: top bar, explorer, main, AI panel, activity. Side panels start
  collapsed there, and every control is at least 44px tall.
- Landmarks: `header`, `nav` (explorer), `main`, `aside` (AI panel), and a `region` "Activity".

## Elevation and depth

- Level 0: paper. Level 1: sunken, for chrome and quiet blocks. That is all for normal content.
- No shadows on cards, buttons, inputs or panels.
- Dialogs use the overlay shadow and a 40% ink scrim.

## Shapes

- `rounded-sm` (4px): buttons, inputs, selects, checkboxes, badges, nav items, messages.
- `rounded-lg` (8px): dialogs, cards, code blocks, empty states, banners.
- Nothing is pill-shaped. No other radii.

## Focus and motion

- Focus: a 2px `accent` outline with 2px offset on every focusable element (`:focus-visible`).
  Never removed, never replaced by a colour change alone.
- Motion: 150ms ease-out on colour, background and border only. No movement, no infinite
  animation except the spinner and the skeleton pulse. `prefers-reduced-motion` turns all
  animation and transitions off.

## Components

All shared pieces are in `frontend/src/components/ui`. Feature code composes them and does not
restyle them.

### Shell
- Top bar: `sunken`, hairline bottom, 48px. "Mantle" in serif 18px links home. Then the project
  name (a link to the project page) and, in a conversation, its title in `muted`.
- Panel header: 36px, title 13px 500 `muted`, a ghost collapse button on the right.

### Sidebar (explorer)
- Group captions ("Projects", "Conversations") are eyebrow labels with a ghost "new" button.
- Items are 32px rows, `rounded-sm`, 8px side padding. Hover: `hover`. Current item: `hover`
  fill, ink text, 500 weight and a 2px `accent` bar on the left. Never a solid ink fill.

### Tabs
- WAI-ARIA tabs. Arrow keys move, Home and End jump, the active tab is the only tab stop.
- Text tabs on a hairline. Active: ink, 500, 2px `accent` underline. Inactive: `muted`.

### Buttons
- Height 32px (28px `sm`), padding 12px (8px `sm`), `rounded-sm`, 14px 500.
- Primary: ink fill, on-ink text; hover ink-2. Secondary: paper, 1px `field` border, ink text;
  hover `hover` fill and ink border. Danger: danger fill, on-danger text. Ghost: no border;
  hover `hover` fill. Icon-only ghost buttons always have an `aria-label`.
- Busy: a spinner replaces the icon, `aria-busy`, disabled.
- Disabled: 50% opacity, `not-allowed` cursor.

### Inputs, select, checkbox and fields
- Inputs and selects: 32px, paper, 1px `field` border, `rounded-sm`, 8px padding. Hover and focus
  darken the border to ink; focus adds the accent ring. Invalid: `danger` border.
- Checkbox: 16px, native control with `accent-color: accent`.
- Field: label (13px 500) above, help (13px `muted`) and error (13px `danger`, with an icon)
  under, linked with `aria-describedby`. Form errors that are not tied to a field sit above the
  submit button.

### Dialog
- Paper, `rounded-lg`, overlay shadow, 24px padding, max width 32rem. Title 20px 500.
- Focus moves in on open (a field with `data-autofocus` first), Tab is trapped, Escape closes,
  focus returns to the opener. The scrim does not close it (no lost input).

### Banner
- `rounded-lg`, soft status fill and ink text. The icon and the kind as a word ("Error:",
  "Warning:", "Note:", "Done:") are in the strong status colour. Danger and warning are `role="alert"`, the rest `role="status"`.
- Copy says what happened and what to do next. Actions sit on the right.

### Badge
- 20px, `rounded-sm`, 12px 500, 6px padding, soft fill with strong text, or a `field` outline
  for neutral. Always a word; an icon is optional.
- Agent origin: info badge with a bot icon and the words "from agent run".
- Run and step statuses (RunBadges): queued and running (info, spinner on running), waiting for
  approval (warning, "needs your approval"), succeeded and approved (success), failed (danger),
  cancelled and rejected (neutral).

### Table
- `Table` component: full width, 13px, a sunken head row with eyebrow labels, hairline row
  rules, 8px cell padding. Numbers right-aligned with `tabular-nums`. Wide tables scroll
  horizontally inside their own box.

### List rows and cards
- A list is rows split by hairlines. A card (`rounded-lg`, 1px hairline border, 12px padding) is
  used only for something the user acts on as a unit: a memory item, a plan item, a key.

### Panel
- See shell. The body scrolls on its own; nothing scrolls the whole page on desktop.

### Empty state
- `rounded-lg`, sunken fill, centred icon (20px `muted`), one sentence that says why it is empty,
  and at most one action.

### Skeleton
- Grey bars in `hover`, a gentle pulse, `role="status"` with a label. No pulse with reduced
  motion.

### Code block
- `CodeBlock`: sunken, `rounded-lg`, mono 13px, scrolls sideways, always `dir="ltr"`. A copy
  button sits top right and says "Copy code", then "Copied" for 1.5s.

### Chat message
- User: sunken fill, `rounded-sm`, aligned with the column. Assistant: no fill, a hairline
  above. The header row holds the author (500) and a status badge: "waiting", "writing",
  "incomplete" or "error".
- Text 15px/24px. Model output is Markdown without raw HTML; links show their real address;
  images are never loaded.

### Composer
- A paper textarea with a `field` border, 3 rows, grows by the user. Enter sends, Shift+Enter is
  a new line. The send button is primary; while streaming it becomes a danger "Stop" button.
  A live region says "Mantle is replying." and "Reply stopped."

### Model picker and switch preview
- Model picker: a select in the top bar with the label "Model". Each option says the window and
  "no key" when needed. Picking a model opens the switch preview; nothing switches without
  "Switch".
- Switch preview dialog: tokens sent of the budget, what is left out, a note when the new model
  must write the summary, a warning when there is no key. "The current model is not called."

### Context report and citations
- The Context tab shows the budget sentence, a `Table` of sections and a list of sources.
- A source is a citation chip: mono 13px `path:lines` on sunken, `rounded-sm`, with its score in
  `muted`. A dropped source adds a warning badge with the reason.

### Progress and cost estimate
- An estimate is a two-column `Table` (row heads on the left). The upper cost bound is named as
  such. Starting a paid run always needs the estimate first and then a confirm.
- A running index or agent run sits in a card with a spinner, the status as a word and
  `aria-live="polite"`. Done, failed and cancelled replace the spinner with an icon and a word.

## State rules

- Status is never colour alone: always a word, and an icon where there is room.
- Every list and panel has four states: loading (skeleton), empty (empty state that says why
  and what to do), error (danger banner with the reason and Retry), and filled.
- Status changes that happen without a click (stream start and end, run progress, saved) are
  announced with `aria-live="polite"` or `role="status"`.
- Text is plain: what happened, then what to do. No "Oops", no exclamation marks.

## Do and don't

- Do keep one primary button per view.
- Do split rows with hairlines before reaching for a box.
- Do right-align numbers and use mono for paths and ids.
- Don't add a colour, a weight, a radius or a shadow that is not in this file.
- Don't use dashed borders, textures, rotated text or decorative labels.
- Don't hard-code colours or font sizes in components.
- Don't load fonts, images or scripts from another origin (the CSP blocks them anyway).

## Responsive behaviour

- 1024px and up: the full three-column shell.
- 768 to 1023px: the same shell; side panels are narrower and can be collapsed.
- Under 768px: one column, side panels start collapsed, 44px touch targets, tables scroll
  sideways. It works at 360px but is not tuned for phones.
