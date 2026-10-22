# Changelog

All notable changes to coachline. Versions follow [semantic versioning](https://semver.org); the version lives in `.claude-plugin/plugin.json`.

## Unreleased

- **A quality meter** on each prompt in the panel: five cells, filled by how concrete the prompt is (a file, an identifier, an error, a number, a link; what done looks like). It is worked out on your machine; nothing is sent.
- **Motion** in the panel: the header shimmers while Claude works, a new analysis unfolds top-down, Copied lights up for a moment. `/coach motion off` keeps every frame still, and it is off by itself with `NO_COLOR`, over SSH or in a terminal too slow to draw it. With motion off the panel no longer redraws ten times a second while Claude works.
- coachline's coral accent: the panel's name chip, the meter and the Copied flash in terminals with 24-bit colour (Windows Terminal, and any that sets `COLORTERM`); the Claude Code pane's name too. The desktop app and the editors keep their own theme.
- coachline's files are written whole or not at all, Claude Code's `settings.json` among them, so a crash or a full disk can no longer leave half a file. Each of coachline's own files carries a version.
- At session start, files of tabs and sessions untouched for 7 days are removed, and the log of analyses keeps its newest 5,000.
- `/coach forget all` deletes what coachline keeps, except your settings and `llm-off.txt`. `/coach doctor` says how much that is.
- The tests hold the local vagueness score to 40 labelled prompts in CI.

## 0.17.0 (2026-10-21)

- **VS Code, Cursor, Windsurf and Antigravity**: with the Claude Code extension, the coachline pane opens beside the Claude Code tab and updates as the analysis and the web finds come in. It is drawn in the editor's own theme, light or dark: its cards and border colour, its accent and text colours, its buttons, Copy first.
- A prompt sent in the desktop app or an editor shows in the pane within seconds, not when the turn ends, and every later prompt of the session shows too (before, only the first one did).
- An editor session never opens the Windows Terminal split.

## 0.16.0 (2026-10-21)

- **The Claude desktop app** (macOS and Windows): the coachline pane opens beside a Code session with your first prompt, and updates as the analysis and the web finds come in. It is drawn in the app's own design: its rounded cards, its text and accent colours in light and dark, and its buttons, Copy first. The terminal's pane and the Windows Terminal panel look and work as before.
- A desktop session's prompts are read from its transcript, since the app writes none to `history.jsonl`; coachline keeps them in `~/.claude/coach/prompts.jsonl` for the analysis and the history review.
- On Windows the pane finds Python through `py -3` when `python3` and `python` are missing or are the Microsoft Store stand-ins. A desktop session never opens the Windows Terminal split.

## 0.15.0 (2026-10-21)

- The Claude Code pane on macOS and Linux shows each part in its own rounded, coloured card, as the Windows panel does: your prompt white, Improve blue, the enhanced prompt cyan, web finds magenta. A web find shows its name in bold, then why, its link and its buttons beneath; bullets wrap under their text.
- The Claude Code pane shows the web research's finds as soon as they come in. It used to stop checking once the analysis was in, so finds that came later waited for the turn to end.
- The Claude Code pane wraps its text once, to its own width: lines are no longer pre-wrapped to the conversation's width and then wrapped again in a narrower side pane.
- The enhanced prompt never cites a paste you didn't make: a sentence pointing at a `[Pasted text …]` marker that isn't in your prompt is dropped, and the model is told not to add one.
- Claude Code's own commands with arguments (`/plugin marketplace add …`, `/model …`) no longer show up in the panel as prompts. A skill called with a task still does.
- The README opens with a screenshot of the panel's cards. The prompt GIF eases in on the panel once the result appears, and a new GIF shows a shoe store website prompt getting a skill to use, an enhanced prompt and web finds. Recorded at twice the size and zoomed with `docs/demo/zoom.py`.
- A new README that shows installing coachline and the panel opening beside Claude Code, then a prompt being improved; install per platform and the must-know keys; the details moved to `docs/` (usage, privacy and accuracy, troubleshooting).
- The install and prompt GIFs are recorded in the real Claude Code, in a separate demo login and a throwaway project; the others use made-up chats (`docs/demo/`). No real data appears in them.
- Contributing guide, code of conduct, security policy, issue and PR templates, Dependabot and `.editorconfig`.
- CI runs on pushes to `main` and on pull requests, with read-only permissions and pinned actions. A release workflow creates the GitHub release from a `coachline--v<version>` tag (`claude plugin tag`).
- Removed the internal design plans and specs (`docs/superpowers/`).

## 0.14.0 (2026-10-13)

- **Web research** once per new task: tools, modern approaches, official docs and reference sites matched to your project's framework versions, each link checked on your machine. Checked links are added to the enhanced prompt as References.
- New panel keys: `x` hides a web suggestion for good, `a` marks one you already use, `r` looks on the web again. What you hid or use is remembered locally, and a suggestion appears with two prompts at most.
- Analysis is on by default everywhere, with separate switches for research (`/coach research on|off`) and a model per pass (`/coach model fast|research haiku|sonnet|opus`).
- The Windows panel shows each part in its own coloured card with header and footer bars, a spinner while Claude works and a Copied flash. Each Windows Terminal tab gets its own panel.
- The enhanced prompt keeps up to 2000 characters and ends at a whole sentence.
- `NO_COLOR` set by Claude Code for its own commands no longer greys out the Windows panel.
- `/coach doctor` says how to switch each setting.
- `eval_suggest.py` measures the suggestion engine on 10 fixed prompts (live, not in CI).

## 0.13.0 (2026-10-02)

- coachline opens as a native **Claude Code pane** on macOS and Linux (Claude Code 2.1.287+), by itself at session start.
- Claude analysis and auto-open are on by default on macOS and Linux; the session-start split is Windows only.

## 0.12.0 – 0.12.5 (2026-10-01)

- The panel gets section bars, a copy button, mouse support and display-width-safe text (CJK and emoji).
- Fixes: the panel is sized from the real terminal, a resumed conversation is shown at once, a fresh session starts empty, and the Improve section is never cut off.

## 0.10.0 – 0.11.1 (2026-10-01)

- The panel shows **this thread only**, analysed by Claude, as a card for the selected prompt plus a compact status list. The statusline is gone.
- Background Claude jobs no longer open a terminal window on Windows.

## 0.8.0 (2026-09-30)

- Pick a prompt in the panel, enhance it, read it in full and copy it to the clipboard.
- Web discovery of better tools, verified locally before display.
- `--help` and unknown options never act.

## 0.1.0 – 0.7.0 (2026-09-29)

- First release: a statusline prompt coach for Claude Code.
- `/coach review` learns your repeated mistakes and requests from your history through your Claude subscription.
- A live panel for the current thread, an advisor for skills, plugins, tips and workflow per task, and an update hook.
