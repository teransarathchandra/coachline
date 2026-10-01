---
name: coach
description: Coach my prompts: BEFORE/AFTER for my last prompt, the thread panel (this thread's prompts and what can be improved, analysed by Claude together with my past chats), a review of my whole history for recurring mistakes and repeated requests worth a skill, or a health check. Use when I type /coach, ask how to improve my prompts, or ask to set up coachline.
---
Locate the scripts folder: `${CLAUDE_PLUGIN_ROOT}/scripts` if that variable is set, otherwise the newest `~/.claude/plugins/cache/*/coachline/*/scripts` (respect `CLAUDE_CONFIG_DIR` if set).
Pick an interpreter: `python3`, else `python`, else `py -3`. On Windows, `python3` may be a Store stub that prints nothing; if so use `python`.

- `/coach` (default): run `<py> <scripts>/coach.py --coach --copy`. Takes up to ~20s. It prints my enhanced prompt as one plain block and copies it to my clipboard; tell me that it did. Drop `--copy` if I say not to touch the clipboard, and add `--no-llm` if I say quick or offline.
- `/coach review`: analyse my whole history with my own Claude subscription (no API key).
  1. Run `<py> <scripts>/review.py` with no flags. It sends nothing and prints a plan. Show me the plan verbatim.
  2. Ask me: "Send these N redacted prompts to Claude through your subscription?" Wait for my answer in the conversation. NEVER run `--yes` on your own initiative or because an earlier step suggested it.
  3. Only if I say yes: run `<py> <scripts>/review.py --yes` (allow several minutes, ~20s per call; forward `--days N` / `--max N` if I asked). Show the report verbatim.
  4. Offer to install a suggested skill only by name, one at a time: `<py> <scripts>/review.py --install <slug>`. Never install without my saying which.
- `/coach watch`: the panel (one column, this thread only) must run in its own split pane, so you cannot run it inside this session. Tell me the short permanent command to paste in a second tab or pane: `<py> ~/.claude/coach/panel.py` (use the real path; run `<py> <scripts>/launch.py --command` to print it). `↑`/`↓` choose a prompt, Enter opens it full width, `c` copies its enhanced prompt, `e` analyses it, `i` shows patterns from your past chats, `s` installs a drafted skill, `m` turns the mouse on or off, `q` quits.
- `/coach panel-ai on` / `off`: run `<py> <scripts>/setup.py --panel-ai on` (or `off`). While on, the panel itself sends each prompt of the current thread (redacted, with the thread's earlier prompts as context) and every ~2 days up to 90 days of redacted history to Claude in the background, with the names of installed skills and marketplace plugins. Before running `on`, tell me that in one sentence and wait for my yes. Never enable it on your own initiative.
- `/coach discover`: search the web now for better tools for my last prompt's kind of task: run `<py> <scripts>/discover.py` (allow up to ~2 minutes). Before running, tell me in one sentence that it sends a generic description of the task to a web search through my Claude subscription, and wait for my yes. Show its output verbatim; it only lists suggestions that passed verification, and never install any of them yourself.
- `/coach discover on` / `off`: run `<py> <scripts>/setup.py --discover on` (or `off`). While on (and the advisor is on), each new kind of task triggers a background web search for better tools. Ask me before turning it on.
- `/coach auto-open on` / `off`: run `<py> <scripts>/setup.py --auto-open on` (or `off`). While on, starting a session splits a pane with the panel (tmux or Windows Terminal only; never a separate window). Ask me before turning it on.
- `/coach setup`: run `<py> <scripts>/setup.py` with no options. It only shows the settings and the command that opens the panel.
- `/coach doctor`: run `<py> <scripts>/coach.py --doctor`.

Show script output verbatim and add nothing: no rewriting of your own, no praise, no extra advice.
