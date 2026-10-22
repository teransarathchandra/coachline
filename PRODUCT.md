# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two audiences, served equally:
- **Claude Code power users**: developers who already work in Claude Code every day, use skills and plugins, and judge a tool by precision, privacy and whether it stays out of the way.
- **Claude Code newcomers**: people still learning how to prompt Claude Code well, who need to see what a good prompt looks like and why.

Their job: get Claude to do the right thing on the first try, without leaving the conversation they are in.

## Product Purpose

coachline is a Claude Code plugin. A panel beside the conversation shows each prompt you send, what it leaves out, and an enhanced version; it puts that version in the prompt box on request, hints as you type, learns which prompts cost you rework, and keeps the prompts that worked first time. Success: fewer interrupted turns and "no, I meant…" follow-ups.

## Positioning

Visible, outside the turn. Other prompt improvers inject hidden instructions into Claude's own turn, spending its tokens where you can't see them. coachline coaches beside the turn, in the open: you see what is missing and fix it before you send.

## Operating Context

- Runs inside Claude Code: a pane on the macOS and Linux terminal, a Windows Terminal split, the Claude desktop app, and the VS Code, Cursor, Windsurf and Antigravity extensions; `/coach watch` in any terminal.
- Analysis runs through the user's own Claude Code login (no API key). Local hints, the meter, the outcome log and the Library are computed on the machine.
- Installed with `/plugin marketplace add teransarathchandra/coachline` and `/plugin install coachline@coachline`. Needs Python 3.9+.

## Capabilities and Constraints

- Features: per-prompt Improve tips and an enhanced prompt with `[ASK: …]` gaps; Use (fills the prompt box, never sends); the hint and quality meter as you type; skills/plugins you have that fit, plus checked web finds for new tasks; patterns from past chats and drafted skills; the outcome evidence line; opt-in hold; the Library of prompts that worked first time.
- Privacy: no telemetry; redaction before anything is sent; `llm-off.txt` keeps a project out; `/coach forget` deletes local data.
- The landing page is static HTML on GitHub Pages (`site/`, deployed by `.github/workflows/pages.yml`, with `docs/assets/` copied in).

## Brand Commitments

- Name: coachline, lower case.
- Visual direction A chosen by the owner: precision tool, near-black `#0B0B0F`, coral accent `#E8735A`, Inter + JetBrains Mono, real product shots of the pane, no stock photography.
- Voice: plain English, concrete, no hype.

## Evidence on Hand

- Media in `docs/assets/`: recordings of the real Claude Code on macOS (install.gif, prompt.gif, screenshot.png) and stills (desktop.png, editor.png); animated illustrations with coachline's real messages (hint, use, hold, newtask); and the standalone panel's own rendered frames (browse, patterns, library). See docs/demo/HANDOFF.md.
- Verifiable facts: MIT licence, zero dependencies, CI on macOS / Linux / Windows × Python 3.9 / 3.13, the live GitHub star count.
- None of: testimonials, customer logos, user counts, benchmarks. Never invent them.

## Product Principles

1. Coach in the open, never inside the turn.
2. The person stays in control: nothing is sent or installed for them.
3. Evidence over opinion: counts are recomputed locally and links checked before they are shown.
4. Private by default: redacted, local where possible, deletable in one command.
5. Stay out of the way: a panel beside the work, not another tool to open.
