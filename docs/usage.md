# Usage

Keep the panel open next to Claude Code and send prompts as usual. It follows the conversation you are in: a new session (or `/clear`) starts empty, and a resumed one shows its prompts at once. A spinner in the header turns while Claude works.

Each prompt gets a card: each part in a rounded box of its own colour, in the Claude Code pane and in the standalone panel alike.

| Part | Colour | What it is |
|---|---|---|
| Your prompt | white | What you sent, with secrets redacted |
| Improve | blue | What the prompt leaves out, and skills of yours that fit the task |
| Enhanced prompt | cyan | A rewrite you can copy, with checked links from web research added as References |
| Worth a look | magenta | Tools, docs and reference sites found on the web for a new task |

Below the card: one line of patterns from your past chats (`i` opens it) and the list of prompts in this thread.

## Keys

| Key | Action |
| --- | --- |
| `↑` `↓` (or `j` `k`) | Choose a prompt |
| `g` / `G` | Oldest / newest prompt |
| `PgUp` `PgDn` | Scroll a long card |
| `Enter` | Open the prompt full width (`Esc` to close) |
| `c` | Copy the enhanced prompt |
| `e` | Ask Claude to analyse the selected prompt now |
| `i` | Show or hide patterns from your past chats |
| `s` | Install the skill Claude drafted for a repeated request (never overwrites) |
| `x` | Hide a web suggestion for good (asks which one when there are several) |
| `a` | Mark a web suggestion as one you already use, so it is not suggested again |
| `r` | Look on the web again for the selected prompt (ignores the cache and a usage-limit pause) |
| `m` | Mouse on or off (off lets you select text with the mouse) |
| `q` | Quit |

With the mouse on, the wheel scrolls and a click selects a prompt or presses a button such as `c Copy`.

## Status marks

| Mark | Meaning |
| --- | --- |
| ✓ | Analysed by Claude |
| … | Being analysed or queued |
| ! | Can be improved (local hint) |
| × | Analysis failed: press `e` to retry |
| – | Project opted out of Claude |
| · | Nothing to add |

## Commands

| Command | What it does |
| --- | --- |
| `/coach` | Enhance your last prompt and copy it to the clipboard |
| `/coach watch` | Print the command that opens the panel in any terminal |
| `/coach review` | Analyse your whole history for repeated requests and mistakes (shows a plan first and sends nothing until you agree) |
| `/coach discover` | Research the web now for your last prompt (ignores the cache and any pause) |
| `/coach panel-ai on\|off` | Turn Claude analysis on or off (on by default) |
| `/coach research on\|off` | Web research once per new task (on by default) |
| `/coach model fast\|research haiku\|sonnet\|opus` | The model for each pass (defaults: fast haiku, research sonnet) |
| `/coach auto-open on\|off` | Open the panel by itself at session start (on by default on macOS and Linux) |
| `/coach setup` | Show the current settings |
| `/coach motion on\|off` | The panel's animations (on by default; off by itself with `NO_COLOR`, over SSH or in a slow terminal) |
| `/coach doctor` | Check that your history, Python and the `claude` CLI work, and how much data coachline keeps |
| `/coach forget all` | Delete everything coachline keeps, except your settings and `llm-off.txt` (asks first) |

## Colour

`NO_COLOR` turns colour off. On Windows, set it in your user environment: the panel ignores the `NO_COLOR` that Claude Code sets for its own commands.
