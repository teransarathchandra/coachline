---
name: coach
description: Show BEFORE/AFTER coaching for my last prompt (5-rule score, repeat detection, Haiku rewrite), install the statusline, or run a health check. Use when I type /coach, ask how to improve my last prompt, or ask to set up coachline.
---
Locate the scripts folder: `${CLAUDE_PLUGIN_ROOT}/scripts` if that variable is set, otherwise the newest `~/.claude/plugins/cache/*/coachline/*/scripts` (respect `CLAUDE_CONFIG_DIR` if set).
Pick an interpreter: `python3`, else `python`, else `py -3`. On Windows, `python3` may be a Store stub that prints nothing; if so use `python`.

- `/coach` (default): run `<py> <scripts>/coach.py --coach`. It takes up to ~20s. Add `--no-llm` if I say quick or offline.
- `/coach setup`: run `<py> <scripts>/setup.py` (installs the statusline; add `--force` only if I say to replace an existing one).
- `/coach doctor`: run `<py> <scripts>/coach.py --doctor`.

Show the output verbatim and add nothing: no rewriting of your own, no praise, no extra advice.
If it reports a REPEAT, offer one line: a draft skill is in `~/.claude/coach/drafts`, and I decide whether to move it.
