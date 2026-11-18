# App design ("grunge-lite")

The look of the Mantle app in `frontend/`. It borrows the palette and personality of
`docs/design-landing.md` (the marketing page), but the app is a tool people read and type in all
day, so the readability rules below win wherever the two disagree.

**Principle: calm, readable, fast.** A developer tool with a grunge personality, not a poster.

## Layout

```
+------------------------------------------------------------------+
| top bar: Mantle | project | model dropdown        | theme | gear |
+-----------+----------------------------------------+-------------+
| explorer  | workspace                              | AI panel    |
| projects  | conversation (chat)                    | memory      |
| convers.  | or settings                            | index       |
|           |                                        | context     |
+-----------+----------------------------------------+-------------+
| activity: calls in this session (model, tokens, cost, purpose)   |
+------------------------------------------------------------------+
```

- Left explorer: projects and their conversations. Center workspace: the conversation, or a
  settings screen. Right AI panel: tabs Memory, Index, Context. Bottom: the activity log.
- The left, right and bottom panels can be collapsed (a button in each header, with
  `aria-expanded`) and the side panels resized with a keyboard-reachable handle (arrow keys).
- Under 768px everything stacks in one column: top bar, workspace, AI panel, explorer, activity.
  Side panels start collapsed there.
- Landmarks: `header`, `nav` (explorer), `main` (workspace), `aside` (AI panel), and a `region`
  named "Activity".

## Colours

The 8 colours of `design-landing.md`, as CSS variables:

| Variable | Name | Hex |
| --- | --- | --- |
| `--faded-black` | Faded Black | `#2E2E2E` |
| `--dirty-yellow` | Dirty Yellow | `#B5A642` |
| `--muted-red` | Muted Red | `#8C2727` |
| `--off-white` | Off-White | `#E9E1D4` |
| `--olive-drab` | Olive Drab | `#6B8E23` |
| `--denim-blue` | Denim Blue | `#3B5998` |
| `--concrete-grey` | Concrete Grey | `#7A7A7A` |
| `--burnt-orange` | Burnt Orange | `#A84700` |

Components never use these directly; they use the theme tokens below. A few tints are added
where a palette colour fails contrast on a background (marked "tint").

| Token | Dark (default) | Light | Use |
| --- | --- | --- | --- |
| `--bg` | `#232323` | Off-White `#E9E1D4` | page background |
| `--surface` | Faded Black `#2E2E2E` | `#F4EFE6` | panels, cards, inputs |
| `--text` | Off-White (12.1:1 on bg) | Faded Black (10.5:1) | body text |
| `--text-muted` | tint `#B3AA9C` (6.9:1 / 5.9:1 on surface) | tint `#5C5650` (5.6:1 / 6.3:1) | secondary text |
| `--border` | Concrete Grey (3.7:1 on bg) | Concrete Grey (3.3:1 on bg, 3.8:1 on surface) | dashed panel borders, input borders |
| `--accent` | Dirty Yellow (6.4:1 on bg) | Denim Blue (5.3:1 on bg) | focus ring, links, active tab |
| `--primary-bg` / `--primary-fg` | Dirty Yellow / Faded Black (5.5:1) | Faded Black / Off-White (10.5:1) | primary buttons |
| `--danger` | tint `#E58B7B` (6.2:1) | Muted Red (6.7:1) | error text, danger outlines |
| `--danger-bg` / `--danger-fg` | Muted Red / Off-White (6.7:1) | same | danger buttons |
| `--warning-bg` / `--warning-fg` | Dirty Yellow / Faded Black (5.5:1) | same | warning banners |
| `--success` | tint `#9DBF5A` (6.5:1 on surface) | Olive Drab, icons and borders only | done, indexed |
| `--info-bg` / `--info-fg` | Denim Blue / Off-White (5.3:1) | same | info badges |

Rules:
- Dirty Yellow is a fill or highlight colour: a background under Faded Black text (5.5:1), or text
  only on Faded Black. Never yellow text on Off-White (1.9:1).
- Concrete Grey and Olive Drab are never used for small text on Off-White (3.3:1, 2.9:1). They
  are fine for borders and icons (3:1 for UI parts).
- Burnt Orange on Off-White is 4.5:1, at the limit: use it for large text or accents only.
- Status never relies on colour alone: every status has an icon and a word ("indexed",
  "skipped", "failed").

## Type

- Courier New (fallback `monospace`), bold, for headings, navigation, buttons, badges, tabs and
  form labels. This is where the grunge personality lives.
- Chat text and long prose: the system UI font (`system-ui, -apple-system, "Segoe UI", sans-serif`),
  15 to 16px, line height 1.6, max about 72 characters per line.
- Code blocks and paths: `Consolas, Menlo, monospace` (not Courier New; it is too thin for long
  code), 14px.

## Borders, texture and decoration

- Panels, cards and empty states: 2px dashed `--border`. Inputs, buttons and focus rings: solid.
- Focus ring: 2px solid `--accent` with a 2px offset, on every focusable element.
- Decoration: a "duct tape" strip or a stamp label (for example "MANTLE" in a panel header, or
  "EMPTY" on an empty state), rotated 2 to 4 degrees. It is `aria-hidden="true"`, holds no text a
  user needs, and is not interactive.
- Noise: an inline SVG `feTurbulence` filter at `--distress-opacity` (0.05 dark, 0.04 light). Only
  on the page background and on empty states.
- Links are underlined.

## Readability rules (these override design-landing.md)

- No flicker. No infinite animation except loading indicators. Everything honours
  `prefers-reduced-motion` (no animation at all then). Motion is 150 to 250ms ease-out.
- Never rotate text that users read or click: messages, buttons, labels, form fields.
- No texture, filter, blur or rotation behind chat text, code, tables or forms. No saturate or
  contrast filters on content.
- WCAG AA: 4.5:1 for text, 3:1 for large text and UI borders, in both themes (ratios above).
- 44px touch targets under 768px. Full keyboard navigation; dialogs trap focus and return it to
  the element that opened them; Escape closes them.

## Components

- Buttons: primary (filled), secondary (solid outline), danger (filled red), ghost (icon only,
  always with an `aria-label`).
- Forms: the label above the input, help text under it, the error under the field in `--danger`
  with an icon, and `aria-describedby` linking them. Submit is disabled while a request runs.
- Loading: skeleton blocks for lists and panels (a gentle pulse, none with reduced motion).
- Empty states: dashed box with noise, one Lucide icon, one sentence, one action.
- Banners: full width at the top of the workspace (for example "Can't reach the Mantle API",
  with a Retry button), with an icon and a word for the kind.
- Badges: Courier New bold, small caps feel, never colour-only.
- Icons: Lucide. No emoji.
- Dark is the default theme; the user can switch, and the choice is kept in `localStorage`
  (the only thing stored there).
