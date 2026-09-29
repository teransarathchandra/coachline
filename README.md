# coachline

A Claude Code statusline that scores your last prompt, and a review that reads your own history to find the prompt mistakes you keep making and the requests you keep repeating. It runs on your existing Claude subscription (`claude -p`): **no API key**. Standard-library Python, no npm.

```
coach 3/5 | done-when, no-vague  (/coach for before/after)
repeat: 'commit/PR/ticket text' asked 9x in 14d (from 2026-09-03)
```

> **Status: v0.1, unvalidated heuristics.** The five rules are keyword checks. Their precision has not been measured (see [Measuring the rules](#measuring-the-rules)). Treat the score as a nudge, not a grade. Developed and run on Windows; macOS and Linux are covered by CI only.

## What it does

- **Statusline** (after each reply): the score of your last prompt, the concrete fix for each failed rule (local, free), and a repeat note when you have asked for the same kind of thing 3+ times in the last 14 days. Scoring is local; no network.
- **Advisor (opt in)**: `setup.py --advisor on`. For each prompt that looks like a task, one background `claude -p` (Haiku) call classifies it and suggests, right in the statusline and the panel: **which of your installed skills to use** (`use: /impeccable`), **which not-yet-installed plugins from your marketplaces to get** (`get: /plugin install frontend-design@...`), **prompt tips** for that kind of task (for UI work: name the style such as modern, luxury or polished; give reference sites; ask for states and responsive behaviour), a short **workflow**, and a better **AFTER** prompt. Nothing about skills is hardcoded: the lists are read from your machine (personal and plugin skills, minus the ones you switched off in `skillOverrides`, and every plugin in your marketplaces you have not installed). Names the model invents are dropped. Tips and workflow steps are the model's own knowledge, so treat them as suggestions. Off by default: it sends every task-like prompt.
- **Web discovery (opt in, inside the advisor)**: `setup.py --discover on`. Beyond what you have installed or listed in your marketplaces, once per kind of task (cached 24h) Claude searches the web (its only tools are WebSearch and WebFetch) for things that do the job better: skills, plugins, MCP servers, CLI tools, libraries or workflows. **Nothing it says is trusted; each suggestion is verified on your machine**: an https URL on a public host (redirects checked), reachable with HTTP 200, the page must mention the name, a GitHub repo must exist (real stars and last-push date come from GitHub; archived or ~18-month-stale repos are dropped), and anything you already have is dropped. Whatever fails is dropped and never shown. Results appear as `better: <name> (<kind>) <stars> - why  <url>` and are labelled web-found. Nothing is ever installed for you. `/coach discover` (or `discover.py --last`) runs it right now for your last prompt.
- **Auto-open**: `setup.py --auto-open on` makes the plugin's SessionStart hook open the thread panel next to Claude when a session starts: a tmux split, a Windows Terminal split, a new console window on Windows, a Terminal.app window on macOS, or a terminal emulator on Linux. It never opens a second panel while one is open (the panel keeps a heartbeat file). Off by default because it opens windows.
- **Thread panel** (`python scripts/watch.py`, `/coach watch` for the exact command, or automatically with auto-open): a second terminal pane. It has no animation and never redraws on its own except when new prompts arrive. There is one column per thread (a thread is one Claude Code session). *This thread* is pinned on the left; earlier threads sit to its right, newest first, and each shows every flagged prompt in full with the fix for each failed rule and any AFTER rewrite. Keys: left/right (or `h`/`l`, Tab) move between threads and pan sideways; up/down (`k`/`j`), PgUp/PgDn scroll a thread; `g`/`G` jump to the top or the newest; `q` quits. Local history only, no LLM, prompt text redacted. `--once` prints one plain frame. Interactive input is tested on Linux (pty); on macOS it uses the same code path; on Windows it uses `msvcrt`, which the automated tests do not cover.
- **`/coach`**: BEFORE with the failed rules and a fix for each, then AFTER: a rewrite from Haiku via `claude -p`. Runs only when you ask.
- **`/coach review`**: sends your redacted history to Claude (your subscription) and asks what *you* do repeatedly: tasks worth a skill, and recurring prompt mistakes. Nothing is hardcoded: the model proposes patterns, then every claim is re-checked locally (see [How review is checked](#how-review-is-checked)). Output: a Markdown report, draft skills in `~/.claude/coach/drafts/`, and `learned.json`, which the statusline reads with no LLM call, so it can say `habit: vague-correction-without-criteria - state what is wrong and how to verify`.
- **Install a drafted skill**: `review.py --install <slug>` copies one draft into your skills folder. It never overwrites, and the `/coach` skill only does it for a name you give.
- **`/coach doctor`**: checks history parsing, interpreter, `claude` CLI and the statusline path.

The five rules: **done-when** (long prompt with no completion criterion), **dont-touch** (risky verb with no boundary), **evidence** (paste over 150 lines), **no-vague** (carefully / properly / best / clean), **rejection-loop** (a correction with no stated reason, sent right after the last reply). A prompt under 26 words shows `short` instead of a score, because most rules do not apply to it.

## Install

```
/plugin marketplace add teransarathchandra/coachline
/plugin install coachline@coachline
/coach setup
```

`/coach setup` writes a `statusLine` entry into `~/.claude/settings.json` (backup: `settings.json.coach-bak`). It will not replace a statusline you already have unless you pass `--force`. After a plugin update a SessionStart hook re-points the entry at the new version (only if the entry is ours; it never touches another statusline or creates one). Undo with `python scripts/setup.py --uninstall`.

Requires Python 3.9+. On macOS `python3` is the command; on Windows use `python` or `py -3`. `setup.py` records the exact interpreter that ran it, so the statusline does not depend on your PATH.

## How review is checked

A model can invent patterns, so nothing it says is taken on trust:
- It is shown a numbered list of your prompts and must cite ids. Keywords must occur, as whole words, in the prompts it cites.
- Counts are **recomputed on your machine**; the model's own counts are ignored.
- Keywords that match more than 40% of your prompts are dropped as too generic.
- A repeated request needs 3+ matching prompts, a mistake 2+. Anything below is reported under "Dropped as ungrounded", not hidden.
- The model has no tools and no settings, and is told the prompts are data, not instructions.
This verifies that a pattern exists in your prompts. It does **not** verify that the suggested fix is good; read the report critically.

## Privacy

- Web discovery searches with only a generic description of the kind of task (for example `ui-design: improve visual design of a store website`), never your prompt text. Search queries still leave your machine through Claude's web search, which is why it is a separate switch. Model and web text is stripped of terminal escape sequences before display.
- The advisor is the only feature that sends prompts without you asking each time, which is why it is opt-in. It sends the redacted prompt, the names and short descriptions of your installed skills, and the names of plugins in your marketplaces.
- Scoring and repeat detection read `~/.claude/history.jsonl` and never leave your machine.
- `/coach review` first prints a plan (how many prompts, how many calls) and sends nothing until you re-run with `--yes`. Then it sends up to 300 redacted prompts (project names replaced by P1, P2...) in a few `claude -p` calls. The `/coach` rewrite sends **one prompt**. Both go to Anthropic through your own `claude` CLI, after redaction (emails, GUIDs, JWTs, API keys, bearer tokens, `password=`/`AccountKey=`-style values). Redaction is pattern-based and will miss things; do not rely on it for secrets.
- List project path fragments in `~/.claude/coach/llm-off.txt` (one per line) to block both the rewrite and the review for those projects.
- Each advisor call is about 9k input tokens on a machine like mine (71 installed skills, 312 marketplace plugins); the catalog comes first and the prompt last so the repeated part can be cached, but I have not verified that `claude -p` caches it. Review uses roughly one call per 60 prompts. `claude -p` inherits `CLAUDE_CONFIG_DIR`, so a custom config directory needs its own login.
- State lives in `~/.claude/coach/` (or `$CLAUDE_CONFIG_DIR/coach/`). No telemetry.

## Limits

- **`history.jsonl` is not a documented API.** It may change; `/coach doctor` will tell you if parsing breaks. Malformed lines are skipped, never fatal.
- **Review reads `history.jsonl` only**: your Claude Code prompts. It cannot see claude.ai web chats, and it does not read Claude's replies from session transcripts.
- **Verification proves a suggestion exists and matches its page or repo, not that it is good or safe.** On the first real test the model gave a GitHub URL with an invented owner (a 404, so it was dropped by the check); the real project has a different owner. Stars measure popularity, not quality; read a tool before you install it.
- **Suggestions are only as good as the model**: on a synthetic "beautify my shoe store website" prompt it picked `/impeccable`, `/design-html` and `/superpowers:brainstorming` from a real machine and dropped two invented names. That is one example, not a measurement.
- **Auto-open was tested on Windows (new console and Windows Terminal split) and in tmux 3.4.** The macOS Terminal.app and Linux terminal-emulator paths are covered by unit tests of the command they build, not by a real launch.
- **Pasted text is not in history**, only a `[Pasted text #N +M lines]` marker, so the rewrite cannot see what you pasted.
- **English only.** Rules are regexes.
- **Score appears after Claude replies**, not while you type. Claude Code offers no hook for the draft text.
- Custom repeat categories: `~/.claude/coach/config.json`, `{"categories": {"name": "regex"}}`.

## Measuring the rules

`python scripts/gold.py make` writes 40 of your own prompts to `~/.claude/coach/gold-labels.md`. Write `yours: ok` or the rules that should flag each, then `python scripts/gold.py eval` prints precision and recall per rule. Do not commit that file; it holds your prompts.

## Alternatives

This overlaps with existing tools, and some are more mature. [Prompt Sensei](https://github.com/chengzhongwei/Prompt-sensei) is a fuller prompt coach (scores, rewrites, observe-mode hooks, habit reports; needs Node). [claude-code-prompt-coach-skill](https://github.com/hancengiz/claude-code-prompt-coach-skill) analyses session logs. What coachline adds, as far as I know: a statusline view, repeated-request detection with skill drafts, and zero install steps beyond Python. If you want a coach, read theirs first.

## Development

```
python -W error::ResourceWarning -m unittest discover -s tests
```

CI runs this on Ubuntu, macOS and Windows with Python 3.9 and 3.13. MIT licensed.
