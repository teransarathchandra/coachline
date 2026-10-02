# coachline

[![ci](https://github.com/teransarathchandra/coachline/actions/workflows/ci.yml/badge.svg)](https://github.com/teransarathchandra/coachline/actions/workflows/ci.yml)
![license](https://img.shields.io/badge/license-MIT-blue)

A side panel for [Claude Code](https://claude.com/claude-code) that coaches your prompts.

It sits in a split pane next to Claude, shows the prompts of your current conversation, and tells you how each one can be better. It also hands you an enhanced version you can copy and paste. Claude does the analysis through your own subscription: **no API key**.

```
  coachline · this thread · 12 prompts                         ● Claude on
 ───────────────────────────────────────────────────────────────────────
 ┃ Your prompt                                  15:28 · ✓ analysed
 ┃ make the shoe site look more premium

 ┃ Improve                                                 frontend
 ┃ • Name the pages you want: home, catalog, product, cart.
 ┃ • use /impeccable: design the interface

 ┃ Enhanced prompt                                          c Copy
 ┃ Create a modern luxury website for selling high-end shoes...
 ───────────────────────────────────────────────────────────────────────
 2 patterns from your past chats · i to read
 ───────────────────────────────────────────────────────────────────────
 Prompts in this thread
 › ✓ 15:28  make the shoe site look more premium
 ↑↓ prompt  c copy  e analyse  Enter full  i patterns  q quit  m mouse
```

## Features

- **Per-prompt coaching**: your prompt in white, what to improve in blue, and a complete enhanced prompt with a copy button.
- **Skill suggestions**: Claude reads your past chats and spots requests you keep repeating, so you can turn them into a skill.
- **Research for each new task**: Claude searches the web for tools, modern approaches, official docs and reference sites that would make the result better (not only what you already have), matched to your project's framework versions. Every link is checked on your machine before you see it.
- **Remembers what it showed you**: a suggestion appears with two prompts at most, never again once you hide it or say you use it, and its checked links are added to the enhanced prompt as References, so Claude Code gets them with your task.
- **Keyboard and mouse**: arrows or wheel to move, click to select, click `c Copy` to copy.
- **Opens by itself**: on macOS and Linux the panel appears inside Claude Code as soon as you start; nothing to set up.

## Requirements

- Claude Code, signed in with your Claude subscription (the `claude` command works in your terminal)
- Python 3.9 or newer (`python3` on macOS and Linux, `python` or `py -3` on Windows)
- Windows, macOS or Linux
- Claude Code 2.1.287 or newer for the built-in pane (older versions: use `/coach watch`)

## Install

In Claude Code:

```
/plugin marketplace add teransarathchandra/coachline
/plugin install coachline@coachline
```

Restart Claude Code.

On macOS and Linux that is all: the panel opens inside Claude Code (from 144 columns at start, otherwise with your first prompt), and Claude analysis and web research are on. Turn either off with `/coach auto-open off` or `/coach panel-ai off`.

On Windows, Claude analysis is on as well; run `/coach auto-open on` to open the panel in a Windows Terminal split on every session (or use the command from `/coach watch`).

## Usage

Keep the panel open next to Claude Code and send prompts as usual. The panel follows the conversation you are in: a new session starts empty, and a resumed one shows its prompts at once.

### Keys

| Key | Action |
| --- | --- |
| `↑` `↓` (or `j` `k`) | Choose a prompt |
| `g` / `G` | Oldest / newest prompt |
| `PgUp` `PgDn` | Scroll a long card |
| `Enter` | Open the prompt full width (`Esc` to close) |
| `c` | Copy the enhanced prompt |
| `e` | Ask Claude to analyse the selected prompt now |
| `i` | Show or hide patterns from your past chats |
| `s` | Install the skill Claude drafted for a repeated request |
| `x` | Hide a web suggestion for good (asks which one when there are several) |
| `a` | Mark a web suggestion as one you already use, so it is not suggested again |
| `r` | Look on the web again for the selected prompt (ignores the cache and a usage-limit pause) |
| `m` | Mouse on or off (off lets you select text with the mouse) |
| `q` | Quit |

With the mouse, the wheel scrolls and a click selects a prompt or presses a button.

### Status marks

| Mark | Meaning |
| --- | --- |
| ✓ | Analysed by Claude |
| … | Being analysed or queued |
| ! | Can be improved (local hint) |
| × | Analysis failed, press `e` to retry |
| – | Project opted out of Claude |
| · | Nothing to add |

### Commands

| Command | What it does |
| --- | --- |
| `/coach` | Enhance your last prompt and copy it to the clipboard |
| `/coach watch` | Print the command that opens the panel |
| `/coach panel-ai on\|off` | Turn Claude analysis on or off (on by default) |
| `/coach review` | Analyse your whole history for repeated requests and mistakes (shows a plan first, sends nothing until you agree) |
| `/coach discover` | Research the web now for your last prompt (ignores the cache and any pause) |
| `/coach research on\|off` | Web research once per new task (on by default; `/coach discover on\|off` is the old name) |
| `/coach model fast\|research haiku\|sonnet\|opus` | The model of each pass (defaults: fast haiku, research sonnet) |
| `/coach auto-open on\|off` | Open the panel by itself at session start (on by default on macOS and Linux) |
| `/coach setup` | Show the current settings |
| `/coach doctor` | Check that history, Python and the `claude` CLI work |

## Privacy

- Analysis and web research are **on by default**. Turn them off with `/coach panel-ai off` (or only research with `/coach research off`); then only built-in local hints run, on your machine. The panel says so in your first three sessions.
- With it on, the panel sends Claude your prompts with emails, keys, tokens and secrets removed, plus up to five earlier prompts of the same conversation. Once on the first run, then every ~2 days, it also sends up to 90 days of history for the pattern analysis, with project names replaced by `P1`, `P2`.
- Pasted content is never sent, only the `[Pasted text #1 +28 lines]` marker.
- List folder names in `~/.claude/coach/llm-off.txt` (one per line) and those projects are never sent.
- Web research sends a short generic task topic, your project's framework names and major versions (read from package.json, pyproject.toml, requirements.txt, go.mod or Cargo.toml; only well-known public frameworks and libraries, never your own packages) and the names of your installed skills. Never your prompt, code, paths or project name. It runs once per new task; a usage limit pauses it until the reset time.
- What you hid or use is kept in `~/.claude/coach/suggestions.json`, on your machine only.
- State is kept in `~/.claude/coach/`. There is no telemetry.

## How it stays accurate

Claude can invent patterns, so its answers are checked on your machine before you see them:

- Keywords must appear in the prompts Claude cites.
- Counts are recomputed locally; Claude's own counts are ignored.
- Skill and plugin names must exist. Every web suggestion needs a live page that names it, GitHub repos must exist and be maintained, and anything made for an older major version than your project uses is dropped.
- A repeated request needs 3 or more matching prompts, a repeated mistake 2 or more.

This shows that a pattern exists. It does not prove the suggested fix is good, so read it critically.

## Limits

- Claude Code's `history.jsonl` is not a documented format and may change. `/coach doctor` tells you if parsing breaks.
- Only Claude Code prompts are analysed, not claude.ai chats or Claude's replies.
- Suggestions are only as good as the model.
- The local hints are five keyword rules, English only.
- The built-in pane needs Claude Code 2.1.287+. On macOS and Linux the panel no longer splits tmux by itself (the pane replaces it); with an older Claude Code, use `/coach watch`. The Windows split was tested on Windows Terminal; `/coach watch` works in any terminal.

## Development

```
python -W error::ResourceWarning -m unittest discover -s tests
python scripts/eval_suggest.py --yes   # live: measures suggestions on 10 fixed prompts (not in CI)
```

CI runs the tests on Ubuntu, macOS and Windows with Python 3.9 and 3.13.

## License

[MIT](LICENSE)
