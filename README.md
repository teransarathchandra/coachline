# coachline

A panel in a split pane next to Claude Code. It shows **this thread's prompts** (white) and **what can be improved** (blue), analysed by Claude on your existing subscription (`claude -p`): **no API key**. It also reads your past chats, so it can tell you when something you keep asking for deserves a skill. Standard-library Python, no npm.

```
  coachline · this thread · 12 prompts                         ● Claude on
 ───────────────────────────────────────────────────────────────────────
 ┃ Your prompt                                  15:28 · ✓ analysed
 ┃ <your prompt, in white>

 ┃ Improve                                                 frontend
 ┃ • tip, short and concrete
 ┃ • use /skill-you-already-have: why

 ┃ Enhanced prompt                                          c Copy
 ┃ <a complete prompt you can paste as it is>
 ───────────────────────────────────────────────────────────────────────
 2 patterns from your past chats · i to read · s installs a skill
 ───────────────────────────────────────────────────────────────────────
 Prompts in this thread
   ✓ 14:59  I just opened a new claude in a terminal, b…
 › ✓ 15:28  No need to open a separate terminal, split p…
 ↑↓ prompt  c copy  e analyse  Enter full  i patterns  s skill  q quit  m mouse
```

> **Status: early.** Claude's analysis is the engine; its output is checked locally (see [How it is checked](#how-it-is-checked)) but the quality of advice varies. The five local rules are keyword heuristics, shown only as a fallback when Claude analysis is off; their precision has not been measured. Developed and run on Windows; macOS and Linux are covered by CI only.

## What it does

- **The panel** (`python ~/.claude/coach/panel.py`, or `python scripts/watch.py`): one column, this thread only (the session of your newest prompt). Your prompts are white, everything that can be improved is blue. No animation; it redraws on a key or when new data arrives. The newest prompt is shown first as a card (your prompt, what to improve, the enhanced prompt); the list below it has one line and one status glyph per prompt (✓ analysed, … analysing, ! can be improved, × failed, – opted out). Each section has a coloured bar on its left (white for your prompt, blue for what to improve). **Keyboard**: `↑`/`↓` (or `j`/`k`) choose a prompt, `g`/`G` oldest/newest, `PgUp`/`PgDn` scroll a tall card, **Enter** opens it full width as plain text, `c` copies its enhanced prompt, `e` has Claude analyse it now, `i` expands the patterns from your past chats, `s` installs a drafted skill, `q` quits. **Mouse** (Windows Terminal, iTerm2, kitty, tmux and most others): the wheel scrolls the list or the card, a click selects a prompt or presses a button (`c Copy`, the footer keys). `m` turns mouse reporting off so you can select text with the mouse, and on again. Wide characters (CJK, emoji) are measured by their display width, so lines never overflow. The footer drops the least important keys instead of wrapping on a narrow pane.
- **From your past chats**: with Claude analysis on, Claude reads your last 90 days of prompts (redacted, a couple of calls) every ~2 days and finds the **requests you repeat** and the **mistakes you keep making**. The panel shows the ones that also appear in this thread, with counts computed on your machine: for example *you have asked for "merge-prs-and-update" 4x in past chats and 1x here -> make it a skill (a draft is ready: press `s`)*. Drafts are written to `~/.claude/coach/drafts/`; `s` copies one into your skills folder and never overwrites.
- **Per-prompt analysis**: for each new prompt of this thread (the newest first, one at a time, up to the last five), Claude gets the prompt, its three earlier prompts as context, and the names of your installed skills and uninstalled marketplace plugins, and returns the kind of task, which of your skills to use, which plugins to get, prompt tips, a workflow and an **enhanced prompt**. Invented skill or plugin names are dropped. If the answer is not valid JSON it is asked once more.
- **Claude analysis is opt-in**: `python scripts/setup.py --panel-ai on` (or `/coach panel-ai on`) lets the panel start these background jobs itself. Without it the panel still lists your prompts with local rule hints, and `e` analyses one prompt on demand (your key press is the consent). Turn it off with `--panel-ai off`.
- **Web discovery (opt in, inside Claude analysis)**: `setup.py --discover on`. Once per kind of task (cached 24h) Claude searches the web (its only tools are WebSearch and WebFetch) for things that do the job better: skills, plugins, MCP servers, CLI tools, libraries or workflows. **Nothing it says is trusted; each suggestion is verified on your machine**: an https URL on a public host (redirects checked), reachable with HTTP 200, the page must mention the name, a GitHub repo must exist (real stars and last-push date from GitHub; archived or ~18-month-stale repos are dropped), and anything you already have is dropped. Whatever fails is dropped. Nothing is ever installed for you. `/coach discover` runs it now for your last prompt.
- **Auto-open**: `setup.py --auto-open on` makes the plugin's SessionStart hook **split a pane** with the panel next to Claude: a tmux split or a Windows Terminal split. Never a separate window, and never a second panel while one is open. In any other terminal nothing opens by itself; run the short, permanent command `python ~/.claude/coach/panel.py` (the path never changes; a launcher is rewritten after plugin updates) in a second tab or pane.
- **Enhanced prompts and pasted content**: your history keeps only a marker like `[Pasted text #1 +28 lines]`, not what you pasted, and pasted content is never sent. The enhanced prompt keeps the marker where it belongs and does not ask for the paste again; paste your content back at the marker. Placeholders such as `[ASK: ...]` or `<email>` (redacted secrets) are for you to fill in.
- **Clipboard**: Windows uses the Win32 clipboard API (exact text, no byte-order mark); macOS `pbcopy`; Linux `wl-copy`, `xclip` or `xsel`; WSL `clip.exe`; anything else falls back to the OSC 52 terminal sequence (Windows Terminal, iTerm2, kitty, tmux with `set-clipboard on`). `/coach --copy` copies too.
- **`/coach`**: BEFORE with the failed local rules, then Claude's advice and one clean ENHANCED PROMPT block (`--copy` puts it on the clipboard).
- **`/coach review`**: runs the history analysis by hand: a plan first (it sends nothing), then your go-ahead, then the report. `review.py --install <slug>` copies one draft skill into your skills folder, never overwriting.
- **`/coach doctor`**: checks history parsing, the interpreter and the `claude` CLI, and shows the panel settings and the command to open it.

The five local rules (shown as hints when Claude analysis is off): **done-when** (long prompt with no completion criterion), **dont-touch** (risky verb with no boundary), **evidence** (paste over 150 lines), **no-vague** (carefully / properly / best / clean), **rejection-loop** (a correction with no stated reason, sent right after the last reply).

## Install

```
/plugin marketplace add teransarathchandra/coachline
/plugin install coachline@coachline
```

Then, once, in a terminal: `python <plugin>/scripts/setup.py` shows your settings and the command that opens the panel, and `setup.py --panel-ai on` / `--auto-open on` turn on the two things that are off by default (`/coach` can do this for you; it asks first). Old versions put a coachline `statusLine` entry in `~/.claude/settings.json`; the SessionStart hook removes that entry automatically (a statusline of anyone else's is never touched). The statusline is gone: the panel is the interface.

Requires Python 3.9+. On macOS `python3` is the command; on Windows use `python` or `py -3`.

## How it is checked

A model can invent patterns, so nothing it says is taken on trust:
- It is shown a numbered list of your prompts and must cite ids. Keywords must occur, as whole words, in the prompts it cites.
- Counts are **recomputed on your machine**; the model's own counts are ignored.
- Keywords that match more than 40% of your prompts are dropped as too generic.
- A repeated request needs 3+ matching prompts, a mistake 2+. Anything below is reported under "Dropped as ungrounded", not hidden.
- The model has no tools and no settings, and is told the prompts are data, not instructions.
This verifies that a pattern exists in your prompts. It does **not** verify that the suggested fix is good; read the report critically.

## Privacy

- Web discovery searches with only a generic description of the kind of task (for example `ui-design: improve visual design of a store website`), never your prompt text. Search queries still leave your machine through Claude's web search, which is why it is a separate switch. Model and web text is stripped of terminal escape sequences before display.
- Claude analysis (`--panel-ai on`) is the only feature that sends prompts without you asking each time, which is why it is opt-in. It sends redacted prompts (this thread's prompts, plus up to 90 days of history every ~2 days, project names replaced by P1, P2...), the names and short descriptions of your installed skills, and the names of plugins in your marketplaces.
- The panel, the local rules and the counts read `~/.claude/history.jsonl` and never leave your machine.
- `/coach review` first prints a plan (how many prompts, how many calls) and sends nothing until you re-run with `--yes`. Then it sends up to 300 redacted prompts (project names replaced by P1, P2...) in a few `claude -p` calls. The `/coach` rewrite sends **one prompt**. Both go to Anthropic through your own `claude` CLI, after redaction (emails, GUIDs, JWTs, API keys, bearer tokens, `password=`/`AccountKey=`-style values). Redaction is pattern-based and will miss things; do not rely on it for secrets.
- List project path fragments in `~/.claude/coach/llm-off.txt` (one per line) to block both the rewrite and the review for those projects.
- Each advisor call is about 9k input tokens on a machine like mine (71 installed skills, 312 marketplace plugins); the catalog comes first and the prompt last so the repeated part can be cached, but I have not verified that `claude -p` caches it. Review uses roughly one call per 60 prompts. `claude -p` inherits `CLAUDE_CONFIG_DIR`, so a custom config directory needs its own login.
- State lives in `~/.claude/coach/` (or `$CLAUDE_CONFIG_DIR/coach/`). No telemetry.

## Limits

- **`history.jsonl` is not a documented API.** It may change; `/coach doctor` will tell you if parsing breaks. Malformed lines are skipped, never fatal.
- **Review reads `history.jsonl` only**: your Claude Code prompts. It cannot see claude.ai web chats, and it does not read Claude's replies from session transcripts.
- **Verification proves a suggestion exists and matches its page or repo, not that it is good or safe.** On the first real test the model gave a GitHub URL with an invented owner (a 404, so it was dropped by the check); the real project has a different owner. Stars measure popularity, not quality; read a tool before you install it.
- **Suggestions are only as good as the model.** In real tests the history analysis found the repeated requests (for example "merge PRs and update the install") and sensible mistake patterns, and the per-prompt analysis misread a prompt until I added the earlier prompts as context; it can still be generic or wrong. Each prompt is analysed with only the thread's last three prompts as context, not the whole conversation or Claude's replies.
- **Auto-open was tested on Windows (Windows Terminal split) and in tmux 3.4.** Other terminals (macOS Terminal.app, iTerm2, Linux emulators, a plain Windows console) cannot be split from outside, so nothing opens there; use the `panel.py` command.
- **Pasted text is not in history**, only a `[Pasted text #N +M lines]` marker, so the rewrite cannot see what you pasted.
- **English only.** Rules are regexes.
- Custom repeat categories: `~/.claude/coach/config.json`, `{"categories": {"name": "regex"}}`.

## Measuring the rules

`python scripts/gold.py make` writes 40 of your own prompts to `~/.claude/coach/gold-labels.md`. Write `yours: ok` or the rules that should flag each, then `python scripts/gold.py eval` prints precision and recall per rule. Do not commit that file; it holds your prompts.

## Alternatives

This overlaps with existing tools, and some are more mature. [Prompt Sensei](https://github.com/chengzhongwei/Prompt-sensei) is a fuller prompt coach (scores, rewrites, observe-mode hooks, habit reports; needs Node). [claude-code-prompt-coach-skill](https://github.com/hancengiz/claude-code-prompt-coach-skill) analyses session logs. What coachline adds, as far as I know: a split-pane view of the current thread, repeated-request detection with skill drafts, and zero install steps beyond Python. If you want a coach, read theirs first.

## Development

```
python -W error::ResourceWarning -m unittest discover -s tests
```

CI runs this on Ubuntu, macOS and Windows with Python 3.9 and 3.13. MIT licensed.
