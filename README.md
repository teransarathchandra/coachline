# coachline

A Claude Code statusline that scores your last prompt, and a review that reads your own history to find the prompt mistakes you keep making and the requests you keep repeating. It runs on your existing Claude subscription (`claude -p`): **no API key**. Standard-library Python, no npm.

```
coach 3/5 | done-when, no-vague  (/coach for before/after)
repeat: 'commit/PR/ticket text' asked 9x in 14d (from 2026-09-03)
```

> **Status: v0.1, unvalidated heuristics.** The five rules are keyword checks. Their precision has not been measured (see [Measuring the rules](#measuring-the-rules)). Treat the score as a nudge, not a grade. Developed and run on Windows; macOS and Linux are covered by CI only.

## What it does

- **Statusline** (after each reply): the score of your last prompt, the concrete fix for each failed rule (local, free), and a repeat note when you have asked for the same kind of thing 3+ times in the last 14 days. Scoring is local; no network.
- **Auto-rewrite (opt in)**: `setup.py --auto-rewrite on` makes each flagged prompt get a rewritten AFTER (plus a one-line WHY) shown right in the statusline, produced by a background Haiku call on your subscription. One call per prompt, never blocks the UI, never retried in a loop. Off by default because it sends every flagged prompt (redacted, `llm-off.txt` respected) automatically. Turn off with `--auto-rewrite off`.
- **Thread panel** (`python scripts/watch.py`, or `/coach watch` for the exact command): run it in a second terminal pane. It has no animation and never redraws on its own except when new prompts arrive. There is one column per thread (a thread is one Claude Code session). *This thread* is pinned on the left; earlier threads sit to its right, newest first, and each shows every flagged prompt in full with the fix for each failed rule and any AFTER rewrite. Keys: left/right (or `h`/`l`, Tab) move between threads and pan sideways; up/down (`k`/`j`), PgUp/PgDn scroll a thread; `g`/`G` jump to the top or the newest; `q` quits. Local history only, no LLM, prompt text redacted. `--once` prints one plain frame. Interactive input is tested on Linux (pty); on macOS it uses the same code path; on Windows it uses `msvcrt`, which the automated tests do not cover.
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

- Auto-rewrite is the only feature that sends prompts without you asking each time, which is why it is opt-in.
- Scoring and repeat detection read `~/.claude/history.jsonl` and never leave your machine.
- `/coach review` first prints a plan (how many prompts, how many calls) and sends nothing until you re-run with `--yes`. Then it sends up to 300 redacted prompts (project names replaced by P1, P2...) in a few `claude -p` calls. The `/coach` rewrite sends **one prompt**. Both go to Anthropic through your own `claude` CLI, after redaction (emails, GUIDs, JWTs, API keys, bearer tokens, `password=`/`AccountKey=`-style values). Redaction is pattern-based and will miss things; do not rely on it for secrets.
- List project path fragments in `~/.claude/coach/llm-off.txt` (one per line) to block both the rewrite and the review for those projects.
- Review uses your subscription quota, roughly one call per 60 prompts. `claude -p` inherits `CLAUDE_CONFIG_DIR`, so a custom config directory needs its own login.
- State lives in `~/.claude/coach/` (or `$CLAUDE_CONFIG_DIR/coach/`). No telemetry.

## Limits

- **`history.jsonl` is not a documented API.** It may change; `/coach doctor` will tell you if parsing breaks. Malformed lines are skipped, never fatal.
- **Review reads `history.jsonl` only**: your Claude Code prompts. It cannot see claude.ai web chats, and it does not read Claude's replies from session transcripts.
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
