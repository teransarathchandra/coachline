# Changelog

All notable changes to coachline. Versions follow [semantic versioning](https://semver.org); the version lives in `.claude-plugin/plugin.json`.

## Unreleased

- The README opens with a screenshot of the panel's cards. The prompt GIF eases in on the panel once the result appears, and a new GIF shows a shoe store website prompt getting a skill to use, an enhanced prompt and web finds. Recorded at twice the size and zoomed with `docs/demo/zoom.py`.
- The Claude Code pane shows the web research's finds as soon as they come in. It used to stop checking once the analysis was in, so finds that came later waited for the turn to end.
- The Claude Code pane on macOS and Linux shows each part in its own rounded, coloured card, as the Windows panel does: your prompt white, Improve blue, the enhanced prompt cyan, web finds magenta. A web find shows its name in bold, then why, its link and its buttons beneath; bullets wrap under their text.
- The Claude Code pane wraps its text once, to its own width: lines are no longer pre-wrapped to the conversation's width and then wrapped again in a narrower side pane.
- The enhanced prompt never cites a paste you didn't make: a sentence pointing at a `[Pasted text …]` marker that isn't in your prompt is dropped, and the model is told not to add one.
- Claude Code's own commands with arguments (`/plugin marketplace add …`, `/model …`) no longer show up in the panel as prompts. A skill called with a task still does.
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
