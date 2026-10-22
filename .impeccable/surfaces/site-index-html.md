---
version: 1
slug: "site-index-html"
primary_target: "site/index.html"
related_targets: []
---

## Scope

site/index.html, the coachline landing page. Mode: Persuade. Audience: Claude Code power users and newcomers, equally. Action: install (two /plugin commands). Proof: real product output only (pane screenshot crops, real panel frames rendered from watch.py, the README GIFs), live GitHub stars, MIT / zero dependencies / CI on macOS, Linux, Windows × Python 3.9, 3.13. Nothing invented. Constraints: static single HTML on GitHub Pages, direction A tokens, 390 to 1600 px, light and dark.

## Direction contract

THESIS: coachline is something you operate with keys beside Claude's turn, so the page is organised around its keys. It refuses the category default: a centred glow hero, a pill eyebrow and a six-card icon grid.

OWN-WORLD: near-black #0B0B0F ground, coral #E8735A as the key and focus colour, JetBrains Mono for keycaps, commands and real panel output, Inter for prose at reading sizes only. Physical keycaps with a bottom lip and pressed state; hairline 1px rules; real terminal frames; no gradients, no glow, no icon tiles.

STORY: one viewport says what it is and how to install it, then a row of keys. Each key section shows the key, one plain sentence, and that key's effect on real product output. A newcomer learns what each control does; a power user sees it is precise and stays out of the way.

FIRST VIEWPORT: the line "Coach every prompt. Beside the turn, not inside it.", the two install commands with copy, and the keycap row with a press hint, above a real pane screenshot.

SIGNATURE INTERACTION: pressing u, c, e, l, h or Enter on the keyboard (or clicking a keycap) depresses that cap and jumps to its section, where its demo replays once.

RISK: keycaps as navigation can read as a gimmick; it holds only if every key maps to a real control and the demos are real output.

## Unresolved

The Use, hint and Library GIFs from the Mac recordings (docs/demo/HANDOFF.md) will replace the interim real panel renders.

Seed: c6ddf16e (surface, persuade); dealt structure: keycaps (chosen by the owner)
