# coachline

A Claude Code statusline that scores your last prompt and tells you when you keep asking for the same thing. `/coach` shows a before/after on demand. Local-first, standard-library Python, no npm.

```
coach 3/5 | done-when, no-vague  (/coach for before/after)
repeat: 'commit/PR/ticket text' asked 9x in 14d (from 2026-09-03)
```

> **Status: v0.1, unvalidated heuristics.** The five rules are keyword checks. Their precision has not been measured (see [Measuring the rules](#measuring-the-rules)). Treat the score as a nudge, not a grade. Developed and run on Windows; macOS and Linux are covered by CI only.

## What it does

- **Statusline** (after each reply): the score of your last prompt, the failed rules, and a repeat note when you have asked for the same kind of thing 3+ times in 14 days. Scoring is local; no network.
- **`/coach`**: BEFORE with the failed rules and a fix for each, then AFTER: a rewrite from Haiku via `claude -p`. Runs only when you ask.
- **Repeat to skill**: when a request category crosses the threshold, a draft `SKILL.md` is written to `~/.claude/coach/drafts/`. Nothing is installed for you.
- **`/coach doctor`**: checks history parsing, interpreter, `claude` CLI and the statusline path.

The five rules: **done-when** (long prompt with no completion criterion), **dont-touch** (risky verb with no boundary), **evidence** (paste over 150 lines), **no-vague** (carefully / properly / best / clean), **rejection-loop** (a correction with no stated reason, sent right after the last reply). A prompt under 26 words shows `short` instead of a score, because most rules do not apply to it.

## Install

```
/plugin marketplace add <owner>/coachline
/plugin install coachline@coachline
/coach setup
```

`/coach setup` writes a `statusLine` entry into `~/.claude/settings.json` (backup: `settings.json.coach-bak`). It will not replace a statusline you already have unless you pass `--force`. Re-run it after a plugin update, because the plugin folder path can change. Undo with `python scripts/setup.py --uninstall`.

Requires Python 3.9+. On macOS `python3` is the command; on Windows use `python` or `py -3`. `setup.py` records the exact interpreter that ran it, so the statusline does not depend on your PATH.

## Privacy

- Scoring and repeat detection read `~/.claude/history.jsonl` and never leave your machine.
- The `/coach` rewrite sends **one prompt** to Anthropic through your own `claude` CLI, after redaction (emails, GUIDs, JWTs, API keys, bearer tokens, `password=`/`AccountKey=`-style values). Redaction is pattern-based and will miss things; do not rely on it for secrets.
- List project path fragments in `~/.claude/coach/llm-off.txt` (one per line) to block the rewrite for those projects.
- State lives in `~/.claude/coach/` (or `$CLAUDE_CONFIG_DIR/coach/`). No telemetry.

## Limits

- **`history.jsonl` is not a documented API.** It may change; `/coach doctor` will tell you if parsing breaks. Malformed lines are skipped, never fatal.
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
