---
name: coachline
description: A Claude Code plugin that coaches each prompt beside the turn, not inside it.
colors:
  ground: "#0b0b0f"
  ground-raised: "#111117"
  line: "#23232c"
  line-strong: "#2e2e39"
  ink: "#ececf1"
  ink-muted: "#a3a3ae"
  ink-faint: "#8a8a95"
  coral: "#e8735a"
  coral-ink: "#0b0b0f"
  cap: "#1a1a22"
  cap-lip: "#07070a"
  cap-ink: "#ececf1"
  term: "#14141b"
  term-line: "#262631"
  term-area-line: "#3a3a48"
  term-text: "#cdd6f4"
  term-soft: "#bac2de"
  term-dim: "#8b90a8"
  term-blue: "#89b4fa"
  term-cyan: "#94e2d5"
  term-green: "#a6e3a1"
  term-yellow: "#f9e2af"
  term-magenta: "#f5c2e7"
  term-red: "#f38ba8"
  term-chip: "#3a5cc5"
  term-chrome: "#17171f"
  ground-light: "#f7f6f3"
  ground-raised-light: "#efede8"
  line-light: "#dedad3"
  line-strong-light: "#cfcac1"
  ink-light: "#131318"
  ink-muted-light: "#4f4f59"
  ink-faint-light: "#6b6b75"
  coral-light: "#b4402a"
  coral-ink-light: "#ffffff"
  cap-light: "#ffffff"
  cap-lip-light: "#c9c4ba"
typography:
  display:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(40px, 6vw, 74px)"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(28px, 3.4vw, 40px)"
    fontWeight: 600
    lineHeight: 1.08
    letterSpacing: "-0.03em"
  lede:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(17px, 1.6vw, 19px)"
    fontWeight: 400
    lineHeight: 1.55
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
  body-sm:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "14px"
    fontWeight: 500
    lineHeight: 1
  caption:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.6
  mono-cap:
    fontFamily: "JetBrains Mono Full, JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1
  mono-command:
    fontFamily: "JetBrains Mono Full, JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  mono-terminal:
    fontFamily: "JetBrains Mono Full, JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "13.5px"
    fontWeight: 400
    lineHeight: 1.3
  mono-label:
    fontFamily: "JetBrains Mono Full, JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.4
rounded:
  xs: "4px"
  sm: "6px"
  md: "8px"
  cap: "10px"
  lg: "12px"
  board: "14px"
spacing:
  hair: "1px"
  xs: "8px"
  sm: "16px"
  md: "22px"
  gutter-narrow: "16px"
  gutter-wide: "32px"
  section-key: "72px"
  section: "80px"
  section-close: "104px"
  max-width: "1180px"
components:
  keycap:
    backgroundColor: "{colors.cap}"
    textColor: "{colors.cap-ink}"
    typography: "{typography.mono-cap}"
    rounded: "{rounded.cap}"
    size: "64px"
  keycap-pressed:
    backgroundColor: "{colors.cap}"
    textColor: "{colors.coral}"
    rounded: "{rounded.cap}"
    size: "64px"
  keycap-section:
    backgroundColor: "{colors.cap}"
    textColor: "{colors.cap-ink}"
    rounded: "{rounded.cap}"
    size: "52px"
  key-board:
    backgroundColor: "{colors.ground-raised}"
    rounded: "{rounded.board}"
    padding: "22px 20px 18px"
  command-line:
    backgroundColor: "{colors.ground-raised}"
    textColor: "{colors.ink}"
    typography: "{typography.mono-command}"
    rounded: "{rounded.md}"
    padding: "6px 6px 6px 14px"
  button-copy:
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.sm}"
    padding: "7px 9px"
  button-copy-done:
    textColor: "{colors.coral}"
    rounded: "{rounded.sm}"
    padding: "7px 9px"
  button-github:
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "7px 10px"
  button-theme:
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.sm}"
    size: "32px"
  nav-link:
    textColor: "{colors.ink-muted}"
    typography: "{typography.label}"
  tab:
    textColor: "{colors.ink-muted}"
    typography: "{typography.label}"
    padding: "12px 14px 13px"
  tab-selected:
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    padding: "12px 14px 13px"
  chip-optin:
    textColor: "{colors.coral}"
    typography: "{typography.mono-label}"
    rounded: "{rounded.xs}"
    padding: "4px 6px"
  terminal-frame:
    backgroundColor: "{colors.term}"
    textColor: "{colors.term-text}"
    typography: "{typography.mono-terminal}"
    rounded: "{rounded.lg}"
    padding: "22px"
  prompt-box:
    backgroundColor: "{colors.term}"
    textColor: "{colors.term-text}"
    typography: "{typography.mono-command}"
    rounded: "{rounded.lg}"
    padding: "22px"
  prompt-box-area:
    rounded: "{rounded.md}"
    padding: "12px 14px"
---

# Design System: coachline

## Overview

**Creative North Star: "The Keyboard Beside the Turn"**

coachline is a tool you operate with keys, and the system is built from that fact. The ground is a near-black instrument surface; the one warm colour, coral, marks what you can press, what is focused and what just happened. Everything else is hairline rules, grey ink and real product output. The page reads like a precise device spec: a keycap you can press, the plain sentence of what it does, and the actual terminal frame it produces.

Density is calm and documentary. Prose sits in Inter at reading sizes with tight, heavy headlines; anything the user would type, press or see in the product is JetBrains Mono. Depth exists only where it is physical (the keycap's lip) or literal (the terminal window); every other surface is flat, separated by 1px lines and a one-step tonal raise.

The owner confirmed the rejections: no stock photography, no gradients, no glow, no icon tiles. Proof is always the real thing: pane screenshots, recorded GIFs, and terminal frames rendered by the product's own `scripts/watch.py`.

**Key Characteristics:**
- Near-black ground, one coral accent, grey ink in three steps.
- Physical keycaps with a bottom lip and a pressed state are the signature.
- Real terminal output, set in mono, in a dark frame in both themes.
- Hairline 1px rules carry structure; tonal raise, not shadow, separates surfaces.
- Light and dark themes share every rule; only the token values change.

## Colors

One warm accent on a cool, nearly colourless ground; the product's own terminal palette lives only inside terminal frames.

### Primary
- **Keystroke Coral** (`coral`; light theme `coral-light`): the key and focus colour. Focus outlines, the pressed and hovered keycap edge, the `>` prompt glyph in commands, the selected tab's underline, list dashes and surface bullets, the opt-in chip, text selection, the caret, the GitHub star, and the brand chip inside terminal frames. Text on a coral fill uses `coral-ink`. The product's terminal UI uses the same coral (watch.py TRUECOLOR `brand`, `accent`, `flash`), so page and product share one accent.

### Neutral
- **Instrument Black** (`ground`; light `ground-light`, a warm paper): the page ground and sticky top bar.
- **Raised Black** (`ground-raised`; light `ground-raised-light`): one tonal step up, for the key board and command lines.
- **Hairline** (`line`; light `line-light`): section dividers, top bar and footer rules, tab baseline, proof-line rules.
- **Hairline Strong** (`line-strong`; light `line-strong-light`): borders on interactive and framed things: buttons, command lines, keycaps, screenshot frames.
- **Ink / Ink Muted / Ink Faint** (`ink`, `ink-muted`, `ink-faint` and their light pairs): headings and emphasis; body and nav; captions, the second headline line, and the board label.
- **Cap Face / Cap Lip / Cap Ink** (`cap`, `cap-lip`, `cap-ink`; light `cap-light`, `cap-lip-light`): keycap face, the solid lip under it, and its legend.

### Terminal (scoped to terminal frames and the prompt box only)
- **Terminal Ground** (`term`, framed by `term-line`): the dark window behind real panel output and the prompt-box illustration. It does not switch in the light theme; a terminal is dark on both pages.
- **Terminal palette** (`term-text`, `term-soft`, `term-dim`, `term-blue`, `term-cyan`, `term-green`, `term-yellow`): the colours the panel actually renders: body text, secondary, dim metadata, Improve boxes, Enhanced prompt boxes, success, held-prompt notes.

### Named Rules
**The One Warm Key Rule.** Coral is the only chromatic colour outside a terminal frame. It marks what is pressable, focused or just done, never decoration or a section background.

**The Dark Terminal Rule.** Terminal frames and the prompt box stay on `term` in both themes, because they show a terminal. Terminal colours never leak onto the page.

## Typography

**Display Font:** Inter (with ui-sans-serif, system-ui, Segoe UI)
**Body Font:** Inter
**Label/Mono Font:** JetBrains Mono, self-hosted as "JetBrains Mono Full" (400, 700) for full box-drawing coverage, with the Google-hosted JetBrains Mono and ui-monospace behind it.

**Character:** Inter is set tight and heavy for headlines and plain for reading; JetBrains Mono carries everything that is a key, a command or product output. Never the other way round.

### Hierarchy
- **Display** (600, clamp 40 to 74px, line-height 1, -0.04em, balanced wrap): the hero line only. Its second clause steps down to `ink-faint` in the same size.
- **Headline** (600, clamp 28 to 40px, 1.08, -0.03em): every section heading, beside a 52px keycap in key sections.
- **Lede** (400, clamp 17 to 19px, 1.55, max 34em): the hero paragraph, `ink-muted` with `ink` bold-500 emphasis.
- **Body** (400, 16px, 1.6, max 34 to 44em): section prose in `ink-muted`.
- **Body small** (400, 15px): key-section lists, privacy definitions, tab captions.
- **Label** (500, 14px): nav, tabs, proof line, link rows. 12 to 13px 500 for small buttons.
- **Caption** (400, 13px, `ink-faint`): figcaptions, board footnote, footer.
- **Mono cap** (700, 20px; 18px on section caps): keycap legends.
- **Mono command** (400, 14px): install commands and the prompt-box text.
- **Mono terminal** (400, 1.3 line-height; 11.5px under 480px, 12.5px to 999px, 13.5px from 1000px): real panel frames, `white-space: pre`.
- **Mono label** (500, 12px): the opt-in chip and the key board's device label.

### Named Rules
**The Mono Means Real Rule.** Mono is for things you press, type or would see in the product. Prose, headings and buttons that are page UI stay in Inter.

**The Tabular Count Rule.** Numbers that are facts (star count, proof line) use `font-variant-numeric: tabular-nums`.

## Layout

A single centred column, max 1180px, with a 16px gutter that becomes 32px from 720px. Sections are full-bleed bands divided by 1px `line` rules, with vertical padding of 72px (key sections), 80px (closing sections) and 104px / 96px (final call to action). Spacing rhythm clusters at 8, 16, 18, 22 and 32px inside blocks, 36 to 72px between columns.

- **Hero:** one column; from 1000px a 1.08fr / 0.92fr grid with the headline spanning both columns and copy + commands beside the key board, aligned to the bottom. A full-width real screenshot follows 56px below, then the proof line between two hairlines (2-column grid, a spread row from 900px).
- **Key sections:** one column; from 1000px a 5fr / 7fr grid (copy left, demo right, 72px gap).
- **Key board:** 3 columns of keys; 6 columns from 560 to 999px; back to 3 when it sits in the hero column at 1000px+.
- **Terminal frames:** a wide frame and a narrow (42-column) frame are both rendered by the product; the narrow one replaces the wide one under 640px. Frames scroll horizontally rather than wrap.
- **Closing:** screenshot pairs go 2-up from 820px; privacy definitions 2-up from 820px; nav section links appear from 820px.
- **Touch:** on `hover: none` devices the keyboard hint is replaced with "Tap a key".

## Elevation & Depth

Flat by default. Surfaces separate by a one-step tonal raise (`ground` to `ground-raised`) and 1px hairlines. Exactly one object casts shadow, the keycap, because it is a physical key: a solid lip directly below it and a small ambient drop. The top bar is sticky, opaque, with a bottom hairline and no blur or shadow.

### Shadow Vocabulary
- **Key lip, at rest** (`box-shadow: 0 5px 0 var(--cap-lip), 0 8px 14px -6px rgba(0,0,0,.55)`): keycaps only.
- **Key lip, pressed** (`box-shadow: 0 1px 0 var(--cap-lip), 0 2px 4px -2px rgba(0,0,0,.5)` with `translateY(4px)`): the pressed state.
- **Frame flash** (`box-shadow: 0 0 0 1px coral` fading to none over 0.9s): a 1px ring, not a glow, on a terminal frame whose key was pressed.

### Named Rules
**The Only Lip Rule.** The solid offset lip belongs to keycaps. Cards, buttons and frames never get an offset or drop shadow.

## Shapes

Gently squared corners on a short scale: 4px for chips and focus rings, 6px for small buttons, 8px for command lines and the prompt area, 10px for keycaps, 12px for terminal frames, screenshots and the product window, 14px for the key board. Borders are always 1px; the selected tab is the only 2px line. Bullets are drawn, not typed: an 8 x 1px coral dash in key-section lists, a 6px coral square in the surfaces list.

## Components

### Keycap (signature)
A real key you can press, the system's centre.
- **Shape:** 64px square (52px beside section headlines), 10px radius, 1px `line-strong` border, `cap` face, mono 700 legend in `cap-ink`; Enter is a drawn return-arrow SVG.
- **Hover:** border turns coral.
- **Pressed:** drops 4px onto its lip, border and legend turn coral; held for 180ms. Transition 140ms on `cubic-bezier(.16, 1, .3, 1)`.
- **Focus:** 2px coral outline, 3px offset, on the cap rather than the link.
- **Behaviour:** pressing H, E, U, C, L or Enter on the keyboard (ignored inside fields, with modifiers, on repeats, and Enter on a focused control) or clicking a cap presses it, scrolls smoothly to its section, updates the hash, and after 450ms replays that section's demo.

### Ghost Keycap (honest keys)
The same footprint as the keycap with a transparent face, a dashed `line-strong` border and no lip: it marks a control that is not a key in coachline's panel (the automatic hint, Claude Code's own Enter, the pane's Use button). Solid caps are only for the panel's real keys (E, C, L). A two-swatch legend in the board head says which is which. Pressed, a ghost cap scales to .94 instead of dropping.

### Window Chrome
Every demo (terminal frame or prompt-box illustration) sits in one chrome: a 12px-radius `term` box with a hairline `term-line` border and a 10px/16px bar in `term-chrome`, carrying the demo's name in mono (`coachline · standalone panel`, `Claude Code · prompt box`) and a tag. `rendered output` is coral with a solid coral hairline; `illustration` is `term-dim` with a dashed border. The tag is the honesty label; captions only add what the chrome does not say.

### Hero Recording
Above 640px the hero plays the real prompt recording (`assets/prompt.mp4`, 1120x688, muted, looping) with the hero screenshot as poster; it plays only while on screen, never under reduced motion, and has a Pause/Play button (WCAG 2.2.2). Below 640px it is replaced by the pane crop (`screenshot-pane.webp`).

### Key Board
The keys' housing: `ground-raised`, 1px `line` border, 14px radius, a mono 12px `ink-faint` device label row, a 3 or 6 column grid, and a 13px footnote naming the keys with `<kbd>`.

### Terminal Frame
Real panel output, never a mock. A `pre` on `term` with a `term-line` border, 12px radius, 18px padding (22px from 1000px), the product's own colours, horizontal scroll. Content is generated by `docs/demo/site_frames.py` from `scripts/watch.py`. On replay it flashes a coral 1px ring for 0.9s.

### Prompt Box Illustration
A drawing of Claude Code's prompt box, labelled as an illustration in its caption. `term` panel, 22px padding, mono 14px; an inner area with a 1px `term-area-line` border, 8px radius, a dim `>` prompt, and a coral block caret blinking at 1.1s. `[ASK: …]` gaps are bold white on a 24% coral tint. Below it one status line: dim hint with a coral meter, yellow held note, or green sent note.
- **Replay:** when 60% visible (once) or when its key is pressed, the draft types at 42ms per character after 250ms, and the status line fades back in over 350ms.

### Command Line with Copy
`ground-raised`, 1px `line-strong`, 8px radius; a coral `>` prompt (not selectable), the command in mono 14px wrapping anywhere, and a Copy button: Inter 500 12px, `ink-muted`, 1px `line-strong`, 6px radius. Hover lifts text to `ink`; on copy it reads "Copied" in coral with a coral border for 1.6s.

### Navigation
Sticky 56px bar on `ground` with a bottom hairline. Wordmark: coral rounded-square mark plus "coachline" in mono 500 16px. Links Inter 14px `ink-muted`, hover `ink`. A 32px outlined theme toggle and an outlined GitHub button whose star count appears only if GitHub answers.

### Tabs
Inter 500 14px `ink-muted` on a hairline baseline; selected is `ink` with a 2px coral underline. Arrow keys move between tabs.

### Chip (opt-in)
Mono 500 12px coral text, 1px coral border, 4px radius, beside a headline to mark an off-by-default feature.

### Screenshots
Real product captures only, 1px `line-strong` border, 12px radius. The hero window uses the capture's own background (#1e1e2e) and swaps to a pane-only crop under 640px.

### Motion
One easing for everything: `cubic-bezier(.16, 1, .3, 1)`. Motion happens only in response to the reader: the key press, the scroll to its section, and that section's demo replay. `prefers-reduced-motion` removes all transitions, animations, smooth scroll and typing; demos show their final state.

## Do's and Don'ts

### Do:
- **Do** keep coral the only chromatic accent on the page, and use it for pressable, focused and just-done states.
- **Do** set keys, commands and product output in JetBrains Mono, and everything else in Inter.
- **Do** show real product output: screenshots, recordings, and frames rendered by watch.py; label any illustration as one in its caption.
- **Do** keep terminal frames and the prompt box dark (`term`) in both themes.
- **Do** separate surfaces with 1px hairlines and the one-step `ground-raised` raise.
- **Do** give every motion a reader trigger and a reduced-motion final state.
- **Do** ship a narrow terminal frame under 640px instead of shrinking the wide one.

### Don't:
- **Don't** use gradients, glow, or icon tiles.
- **Don't** use stock photography or invented proof.
- **Don't** give anything but a keycap an offset lip or drop shadow.
- **Don't** use terminal colours outside terminal frames and the prompt box.
- **Don't** set prose or headings in mono, or keys and commands in Inter.
