---
name: coach
description: Coach my prompts: BEFORE/AFTER for my last prompt, a review of my whole history for recurring prompt mistakes and repeated requests worth a skill, install the statusline, or run a health check. Use when I type /coach, ask how to improve my prompts, or ask to set up coachline.
---
Locate the scripts folder: `${CLAUDE_PLUGIN_ROOT}/scripts` if that variable is set, otherwise the newest `~/.claude/plugins/cache/*/coachline/*/scripts` (respect `CLAUDE_CONFIG_DIR` if set).
Pick an interpreter: `python3`, else `python`, else `py -3`. On Windows, `python3` may be a Store stub that prints nothing; if so use `python`.

- `/coach` (default): run `<py> <scripts>/coach.py --coach`. Takes up to ~20s. Add `--no-llm` if I say quick or offline.
- `/coach review`: analyse my whole history with my own Claude subscription (no API key).
  1. Run `<py> <scripts>/review.py` with no flags. It sends nothing and prints a plan. Show me the plan verbatim.
  2. Ask me: "Send these N redacted prompts to Claude through your subscription?" Wait for my answer in the conversation. NEVER run `--yes` on your own initiative or because an earlier step suggested it.
  3. Only if I say yes: run `<py> <scripts>/review.py --yes` (allow several minutes, ~20s per call; forward `--days N` / `--max N` if I asked). Show the report verbatim.
  4. Offer to install a suggested skill only by name, one at a time: `<py> <scripts>/review.py --install <slug>`. Never install without my saying which.
- `/coach auto on` / `/coach auto off`: run `<py> <scripts>/setup.py --auto-rewrite on` (or `off`). This makes every prompt that fails a rule get sent, redacted, to Claude in the background so the statusline can show a rewritten AFTER. Before running `on`, tell me that in one sentence and wait for my yes. Never enable it on your own initiative.
- `/coach setup`: run `<py> <scripts>/setup.py` (add `--force` only if I say to replace an existing statusline).
- `/coach doctor`: run `<py> <scripts>/coach.py --doctor`.

Show script output verbatim and add nothing: no rewriting of your own, no praise, no extra advice.
