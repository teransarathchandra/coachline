---
name: coach
description: Coach my prompts: BEFORE/AFTER for my last prompt, a review of my whole history for recurring prompt mistakes and repeated requests worth a skill, install the statusline, or run a health check. Use when I type /coach, ask how to improve my prompts, or ask to set up coachline.
---
Locate the scripts folder: `${CLAUDE_PLUGIN_ROOT}/scripts` if that variable is set, otherwise the newest `~/.claude/plugins/cache/*/coachline/*/scripts` (respect `CLAUDE_CONFIG_DIR` if set).
Pick an interpreter: `python3`, else `python`, else `py -3`. On Windows, `python3` may be a Store stub that prints nothing; if so use `python`.

- `/coach` (default): run `<py> <scripts>/coach.py --coach --copy`. Takes up to ~20s. It prints my enhanced prompt as one plain block and copies it to my clipboard; tell me that it did. Drop `--copy` if I say not to touch the clipboard, and add `--no-llm` if I say quick or offline.
- `/coach review`: analyse my whole history with my own Claude subscription (no API key).
  1. Run `<py> <scripts>/review.py` with no flags. It sends nothing and prints a plan. Show me the plan verbatim.
  2. Ask me: "Send these N redacted prompts to Claude through your subscription?" Wait for my answer in the conversation. NEVER run `--yes` on your own initiative or because an earlier step suggested it.
  3. Only if I say yes: run `<py> <scripts>/review.py --yes` (allow several minutes, ~20s per call; forward `--days N` / `--max N` if I asked). Show the report verbatim.
  4. Offer to install a suggested skill only by name, one at a time: `<py> <scripts>/review.py --install <slug>`. Never install without my saying which.
- `/coach watch`: a keyboard-driven panel that must run in its own terminal pane, so you cannot run it inside this session. Tell me the exact command to paste in a second terminal or split pane: `<py> <scripts>/watch.py` (with the real resolved paths). One column per thread, this thread pinned on the left; left/right move between threads, up/down scroll, `q` quits. No animation, no LLM.
- `/coach advisor on` / `off`: run `<py> <scripts>/setup.py --advisor on` (or `off`). While on, every task-like prompt is sent, redacted, to Claude in the background, together with the names of installed skills and marketplace plugins, so the statusline and panel can suggest skills, plugins, prompt tips and a workflow. Before running `on`, tell me that in one sentence and wait for my yes. Never enable it on your own initiative.
- `/coach discover`: search the web now for better tools for my last prompt's kind of task: run `<py> <scripts>/discover.py` (allow up to ~2 minutes). Before running, tell me in one sentence that it sends a generic description of the task to a web search through my Claude subscription, and wait for my yes. Show its output verbatim; it only lists suggestions that passed verification, and never install any of them yourself.
- `/coach discover on` / `off`: run `<py> <scripts>/setup.py --discover on` (or `off`). While on (and the advisor is on), each new kind of task triggers a background web search for better tools. Ask me before turning it on.
- `/coach panel-hint on` / `off`: run `<py> <scripts>/setup.py --panel-hint on` (or `off`). The statusline's bottom line shows the command that opens the panel while it is not open; this shows or hides it.
- `/coach auto-open on` / `off`: run `<py> <scripts>/setup.py --auto-open on` (or `off`). While on, starting a session opens the thread panel in a new pane or window. Ask me before turning it on, since it opens windows.
- `/coach setup`: run `<py> <scripts>/setup.py` (add `--force` only if I say to replace an existing statusline).
- `/coach doctor`: run `<py> <scripts>/coach.py --doctor`.

Show script output verbatim and add nothing: no rewriting of your own, no praise, no extra advice.
