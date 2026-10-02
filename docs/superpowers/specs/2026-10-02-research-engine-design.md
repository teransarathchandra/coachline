# coachline suggestion engine: research instead of a menu

Date: 2026-10-02 · Status: design agreed in a grilling session, spec awaiting review · Phases: P1 (this plan), P2, P3

## Problem

The per-prompt advice (`scripts/advisor.py`) gives Claude a closed menu: the skills already installed plus the plugins of the
marketplaces the user added, and `validate` drops every name not on it. Haiku has no tools in that call. So every suggestion is
"use something you already have", and the user never hears that a better tool, approach, guideline or reference exists.

Web discovery (`scripts/discover.py`) exists but is off by default, runs once per coarse kind of task (24h cache keyed on
`task:summary-words`), returns at most 3 tools and never docs, guidelines or reference sites.

## Goal

For every distinct task the user starts in Claude Code, the panel shows up to 4 **verified, current** things that would make the
result better: tools (skills, plugins, MCP servers, CLIs, libraries), modern approaches, official docs or guidelines, and live
reference sites. The user's installed skills are one source among many, never the limit. Everything runs on the user's own Claude
subscription through `claude -p`: no API key.

## Decisions (from the grilling session)

| # | Decision |
| --- | --- |
| Q1 | Stronger model for research (sonnet), haiku stays for the fast rewrite. Claude analysis is on by default on **all** platforms, Windows included. Auto-open on Windows stays opt-in. |
| Q2 | Two passes: a fast pass (haiku, no tools) produces the card in seconds; a research pass (web tools) fills "Worth a look" when it lands. |
| Q3 | Installed skills and marketplace plugins are context, not a whitelist. "use"/"get" still only name things that really exist (checked locally). |
| Q4 | Research kinds: `tool`, `tech` (modern approach), `docs` (official docs, guidelines, specs), `inspo` (live example sites). No articles. Max 4 items. |
| Q5 | Every research item has a live URL verified on this machine (the existing checks, extended to every kind). |
| Q6 | Research runs once per distinct task, plus on demand (`/coach discover`). |
| Q7 | The fast pass returns `topic` (≤6 words) and `new_task` (bool, using the earlier prompts). Research runs when `new_task` is true or the session has had none yet. Results are cached per topic + stack for 7 days, across sessions. |
| Q8 | Research sees: the generic topic, kind and summary; the project's stack detected locally from manifest files (public framework names + major versions only); the names of installed skills (to avoid recommending them). Never the prompt, code, paths or project name. `llm-off.txt` projects send nothing. |
| Q9 | "Modern" = maintained (stale GitHub repos still dropped) and matching the stack's major versions: the model is told the versions, and an item that only names an older major of a stack framework is dropped locally. No hard date window. |
| Q10 | (P2) Remember what was shown; show an item at most twice; `x` dismisses for good, `a` marks adopted. (P3) the history review reports adopted/ignored items. |
| Q11 | (P2) When research lands, verified items are appended to the enhanced prompt as a short **References** block and the card marks the prompt as updated. |
| Q12 | Research defaults to sonnet; `/coach model research|fast haiku|sonnet|opus` changes either pass. |
| Q13 | Research is on by default wherever analysis is on. `/coach research on|off`; `/coach discover on|off` is the old alias; `/coach discover` forces a run for the last prompt. |
| Q14 | A usage-limit error pauses research until the reset time Claude names (else one hour); the fast pass continues; the panel shows one dim line. One research job at a time; a newer request replaces any waiting one. |
| Q15 | UI change kept minimal: new kind labels on the existing "better:" lines, the pause line (P1); `x`/`a` keys and the updated mark (P2). No layout redesign. |
| Q16 | Unit tests with the stubbed `claude` and network, plus `scripts/eval_suggest.py`: 10 fixed prompts run live, reporting share of recommendations not already installed, verification pass rate, kind mix and latency. Run before and after. |
| Q17 | Three PRs: P1 engine + eval, P2 memory + References + keys, P3 review integration. |

## P1 scope (this spec's first plan)

### Fast pass (`advisor.py`)

- Prompt: INSTALLED/AVAILABLE are described as "what the user already has", explicitly **not** the limit of good advice; tips and
  workflow recommend whatever is best today. `use`/`get` keep the local existence check.
- New fields: `topic` (≤6 words, lowercase, no names of people, companies or projects) and `new_task` (bool; true when there is
  no earlier prompt). Missing or malformed → `topic` falls back to `summary`, `new_task` to true.
- Model: `coach.model_for("fast")` (default haiku).

### Stack detection (new `stackinfo.py`)

- From the prompt's project folder, walk up (at most 5 levels, stop at a `.git` folder) to the first folder with a manifest:
  `package.json`, `pyproject.toml`, `requirements.txt`, `go.mod`, `Cargo.toml`.
- Output: up to 12 entries like `next@15`, `react@19`, `django@5`, `node`, `python`, `go@1.22`, `rust`. Runtime dependencies before
  dev dependencies.
- Never sent: scoped npm packages outside a fixed list of well-known public scopes, `@types/*`, local / workspace / git / URL
  dependencies, anything not matching a plain package-name pattern. Never raises; unreadable → `[]`.

### Research pass (`discover.py`)

- One `claude -p` call, model `coach.model_for("research")` (default sonnet), tools WebSearch + WebFetch only, timeout 240s.
- Input: topic, kind, summary, stack, installed names. Output: up to 8 raw items `{name, kind, why, url, install}`.
- Kinds `tool|tech|docs|inspo`; the old kinds (`skill`, `plugin`, `mcp`, `library`, `workflow`) map to `tool`. `install` is kept
  for tools only.
- Verification: the existing rules (public https, live page that names the item, real non-archived non-stale GitHub repo, not
  already installed) plus the stack-version rule. At most 4 kept.
- Cache: key `task:sorted topic words|sorted stack`, 7-day TTL.
- Usage limit: a `claude` failure or answer that mentions a usage/rate limit sets `paused_until` (the epoch after `|`, or a
  `resets 2pm` / `resets at 14:00` time, else now + 1h). Paused research is skipped unless forced.

### Queue and trigger (`discover.request`, called from `coach.bg_rewrite`)

- After the fast pass succeeds and research is on: if `new_task` is true or the session has no research yet, write the request to
  `research-want.json` (newest wins) and try to take `research.running` (exclusive create; stale after 10 minutes). The holder
  drains the want file until it holds nothing new, so at most one research call runs and an out-of-date waiting request is dropped.
- The result is appended to `rewrites.jsonl` for that prompt key as today (`discovery` field), and the session is marked researched.

### Settings (`coach.py`, `setup.py`)

- `ai_on()` defaults to on everywhere. The first-sessions notice now also shows on Windows and mentions web research.
- `research_on()`: setting `research`, else old `discover`, else on; always off when analysis is off.
- `model_for(kind)`: setting `model_fast` / `model_research` if one of `haiku|sonnet|opus`, else haiku / sonnet.
- `setup.py --research on|off` (`--discover` alias), `setup.py --model fast|research <model>`; `setup.py` shows them.

### Panel

- The "better:" lines show the new kind labels (no code change beyond the kinds).
- When research is paused, analysed cards show `web research paused until HH:MM (usage limit); the enhanced prompt still works`.

### Eval (`scripts/eval_suggest.py`, not in CI)

- 10 fixed prompts across ui, frontend, backend, debugging, testing, infra, data, docs, refactoring, each with a fixed stack.
- Sends nothing without `--yes`. The baseline is run once before the engine changes, the comparison once after.
- Per prompt and in total: fast and research latency, `use`/`get` counts, raw and verified research counts, kind mix, and the share
  of recommendations not already installed (`(get + verified) / (use + get + verified)`). Written to `<state>/eval/<time>.json`.

## P2 scope (second plan)

Branch `feat/research-memory`, stacked on `feat/research-engine` (PR #23).

### Memory (new `memory.py`, `<state>/suggestions.json`, local only)

- An item's id is its URL without scheme, `www.`, case or trailing slash (the name when there is no URL).
- An item is shown with at most **2** prompts. The research pass picks up to 4 from what it found (it now keeps up to 8 verified),
  skipping hidden, adopted and twice-shown items, and records the prompt each one was shown with.
- `x` hides an item for good (`dismissed`); `a` marks it as one you already use (`adopted`). Neither is suggested again. Choices
  are never forgotten; at most 500 unmarked items are kept.
- A hidden item also disappears at once from cards that already show it.

### References in the enhanced prompt

- When research lands, the card's enhanced prompt (and what `c` / the pane's Copy button copies) ends with a block:
  `References (checked links from web research):` then one line per shown item: `- Use|Consider|Follow|Take visual cues from <name>: <url>`
  for tool|tech|docs|inspo. It is built at display time from the items not hidden, so hiding one updates the copy too.
- The card says so under the enhanced prompt (the "updated" mark): `Includes references from web research: x hides one, a marks one
  you use, r looks again.` The pane shows Hide / I use this buttons per item and a Look again button instead.

### Keys and buttons

- Panel: web items are numbered. `x` / `a` act at once when there is one item, else ask `press 1-N` (Esc or any other key cancels).
  `r` researches the selected prompt again now (fresh: ignores the cache and a usage-limit pause; still never for `llm-off.txt`).
- Pane: `pane.py --mark dismissed|adopted ID` and `pane.py --research KEY [--session S]`, behind per-item Hide / I use this buttons and a
  Look again button.
- The footer keys do not change (they are tested at fixed widths); the card line names the new keys.

### Fixes carried into P2

- The standalone panel did not redraw when research landed (its change signature ignored research): it now counts research items and
  the pause.

## Privacy changes (README must say so)

Research sends a generic topic, a summary, the stack (framework names + major versions) and installed skill names to a web-search
call through the subscription. It is now on by default wherever analysis is on, and analysis is on by default on Windows too.

## Out of scope for P1

Show-count memory, dismiss/adopt keys, References block, the "updated" mark, review integration, any TUI redesign.

## Success criteria for P1

1. On a fresh install (any OS) a new task's card gets a "Worth a look" section with up to 4 verified items, without any setting.
2. Follow-up prompts of the same task make no web call.
3. A usage-limit failure pauses research and the panel says until when; the fast pass keeps working.
4. The eval shows a higher share of not-installed recommendations than the baseline, with a verification pass rate reported.
5. `python -W error::ResourceWarning -m unittest discover -s tests` is green on Ubuntu, macOS and Windows.
