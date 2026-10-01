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
- **Better tools**: points to skills and plugins you already have, or could install, that fit the task.
- **Keyboard and mouse**: arrows or wheel to move, click to select, click `c Copy` to copy.
- **Private by default**: nothing is sent to Claude until you turn analysis on.

## Requirements

- Claude Code, signed in with your Claude subscription (the `claude` command works in your terminal)
- Python 3.9 or newer (`python3` on macOS and Linux, `python` or `py -3` on Windows)
- Windows, macOS or Linux

## Install

In Claude Code:

```
/plugin marketplace add teransarathchandra/coachline
/plugin install coachline@coachline
```

Restart Claude Code. Then:

```
/coach watch          # prints the command that opens the panel; run it in a second pane or tab
/coach panel-ai on    # let Claude analyse your prompts (it asks first)
```

To open the panel automatically in a split pane on every session, run `/coach auto-open on`. This works in Windows Terminal and tmux. Everywhere else, use the command from `/coach watch`.

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
| `/coach panel-ai on\|off` | Turn Claude analysis on or off |
| `/coach review` | Analyse your whole history for repeated requests and mistakes (shows a plan first, sends nothing until you agree) |
| `/coach discover` | Search the web now for better tools for your last prompt |
| `/coach discover on\|off` | Search the web automatically, once per kind of task (needs analysis on) |
| `/coach auto-open on\|off` | Open the panel in a split pane at session start |
| `/coach setup` | Show the current settings |
| `/coach doctor` | Check that history, Python and the `claude` CLI work |

## Privacy

- Analysis is **off** until you run `/coach panel-ai on`. With it off, only built-in local hints run, on your machine.
- With it on, the panel sends Claude your prompts with emails, keys, tokens and secrets removed, plus up to five earlier prompts of the same conversation. Every ~2 days it also sends up to 90 days of history for the pattern analysis, with project names replaced by `P1`, `P2`.
- Pasted content is never sent, only the `[Pasted text #1 +28 lines]` marker.
- List folder names in `~/.claude/coach/llm-off.txt` (one per line) and those projects are never sent.
- Web discovery sends only a generic description of the task, never your prompt.
- State is kept in `~/.claude/coach/`. There is no telemetry.

## How it stays accurate

Claude can invent patterns, so its answers are checked on your machine before you see them:

- Keywords must appear in the prompts Claude cites.
- Counts are recomputed locally; Claude's own counts are ignored.
- Skill and plugin names must exist. Web suggestions need a live page, and GitHub repos must exist and be maintained.
- A repeated request needs 3 or more matching prompts, a repeated mistake 2 or more.

This shows that a pattern exists. It does not prove the suggested fix is good, so read it critically.

## Limits

- Claude Code's `history.jsonl` is not a documented format and may change. `/coach doctor` tells you if parsing breaks.
- Only Claude Code prompts are analysed, not claude.ai chats or Claude's replies.
- Suggestions are only as good as the model.
- The local hints are five keyword rules, English only.
- Auto-open was tested on Windows Terminal and tmux. Other terminals cannot be split from outside.

## Development

```
python -W error::ResourceWarning -m unittest discover -s tests
```

CI runs the tests on Ubuntu, macOS and Windows with Python 3.9 and 3.13.

## License

[MIT](LICENSE)
