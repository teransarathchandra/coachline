# Privacy and accuracy

coachline runs on your machine. When Claude analysis is on, it calls the `claude` CLI you are already signed in to, so it uses your own subscription: no API key, no server of ours, no telemetry.

## What is sent to Claude

Analysis and web research are **on by default**. The panel says so in your first three sessions.

| When | What is sent |
|---|---|
| Each prompt of the current thread | The prompt with emails, keys, tokens and secrets removed, plus up to five earlier prompts of the same conversation as context |
| First run, then about every 2 days | Up to 90 days of redacted history for the pattern analysis, with project names replaced by `P1`, `P2`, … |
| Once per new task (web research) | A short generic task topic, your project's framework names and major versions, and the names of your installed skills |

Web research reads framework versions from `package.json`, `pyproject.toml`, `requirements.txt`, `go.mod` or `Cargo.toml`, and only for well-known public frameworks and libraries, never your own packages. It never sends your prompt, code, paths or project name. A usage limit pauses it until the reset time.

Never sent:

- Pasted content: only the `[Pasted text #1 +28 lines]` marker.
- Projects listed in `~/.claude/coach/llm-off.txt` (one folder name per line).

## Turning it off

| Command | Effect |
|---|---|
| `/coach panel-ai off` | Nothing is sent; only the built-in local hints run |
| `/coach research off` | Analysis stays on; web research stops |

## What stays on your machine

Everything coachline keeps is in `~/.claude/coach/`, including `suggestions.json` (what you hid or marked as used). `/coach doctor` says how much that is; `/coach forget all` deletes it, keeping only your settings and `llm-off.txt`, so a project you kept private stays private. Files of tabs and sessions untouched for 7 days are removed at session start, and the log of analyses keeps its newest 5,000.

## How answers are checked

Claude can invent patterns, so its answers are checked on your machine before you see them:

- Keywords must appear in the prompts Claude cites.
- Counts are recomputed locally; Claude's own counts are ignored.
- A repeated request needs 3 or more matching prompts, a repeated mistake 2 or more.
- Skill and plugin names must exist.
- Every web suggestion needs a live page that names it. GitHub repos must exist and be maintained, and anything made for an older major version than your project uses is dropped.

This shows that a pattern exists. It does not prove the suggested fix is good, so read it critically.
