# coachline as a native Claude Code pane (macOS and Linux)

Date: 2026-10-02 · Branch: `feat/macos-pane` · Status: design approved in chat, spec awaiting review

## Goal

A user installs coachline from the marketplace, starts Claude Code, and the panel is there beside the conversation. They run no
command, change no setting and need not know the feature exists. Anyone who does not want it turns it off.

## Users and constraints

- Users are assumed never to read the README or run `/coach` subcommands. Every feature the panel needs is **on by default**, each
  with an off switch.
- **Windows does not change.** The Windows Terminal split (`launch.py`, the `wt.exe` branch), its opt-in auto-open and its current
  defaults stay exactly as they are.
- Apple Terminal (the default macOS terminal) cannot be split by a script, so a split-pane approach cannot reach these users. The pane
  is drawn by Claude Code itself, through a plugin hooks module (`$.ui.open` + a `ui.render` hook on `Pane`), which works in any
  terminal.
- The hooks-module API is early access and moves between Claude Code releases. Everything that works today must keep working if the
  module fails to load.

## Success criteria

1. Fresh macOS install from the marketplace, Claude Code restarted, first prompt sent: the pane is visible at any terminal width,
   showing that prompt, with no command run by the user.
2. At 144+ columns the pane is already visible at session start, before the first prompt.
3. With Claude analysis on by default, the selected prompt gets an enhanced prompt in the pane without the user pressing anything.
4. `/coach auto-open off` stops the pane from opening; `/coach panel-ai off` stops all sending to Claude. Closing the pane by hand
   keeps it closed for the rest of that session.
5. On Windows, behaviour is byte-for-byte what it is today: the module opens nothing, and defaults are unchanged.
6. The existing Python test suite stays green; new Python and `claude plugin test` tests cover the new code.

## When the pane opens

| Moment | Call | Placed |
| --- | --- | --- |
| `session.start` | `$.ui.open({ id: "coachline", title: "coachline" })` | from 144 columns (110 if the user opened it before and has not closed it by hand); below that it waits undrawn |
| the user's first `prompt.submit` of the session, if the pane is not placed yet | the same call | at any width: an open in the hook of a prompt the person entered counts as asked |

The module does nothing when: the platform is Windows (`$.env.get("OS") === "Windows_NT"`), the `auto_open_watch` setting is
`false`, or the user closed the pane by hand this session (a `ui.close` with `origin: "person"`, kept in `$.state`).

On macOS and Linux, `launch.py --auto` (the SessionStart command hook) no longer splits tmux, so a tmux user never gets two panels.
`launch.py` run by hand still splits tmux. Windows takes its existing path unchanged.

## Shape

```
hooks/hooks.json          + "modules": ["./coachline.tsx"]   (the existing SessionStart command hooks stay)
hooks/coachline.tsx       new: opens the pane, draws it, handles its buttons; holds no coaching logic
types/index.d.ts          new: the module's $.state contract
scripts/pane.py           new: one tick of the panel without drawing; prints the panel's state as JSON
scripts/watch.py          build() gains an optional session override; nothing else changes
scripts/coach.py          setting defaults become platform-aware (see Defaults)
```

### `scripts/pane.py`

`python3 pane.py --json --session <id>`:

1. `watch.build(HIST)`, with the session forced to `<id>` (the module knows the real session id, so no guessing from
   `current-session.json`).
2. `watch.autopilot(st, ui)`, where `ui` (`pending`, `tried`, `review_after`) is loaded from and saved to
   `~/.claude/coach/pane-<session>.json`, because each tick is a fresh process. It is skipped when a standalone panel is open
   (`coach.panel_alive()`), so two autopilots never queue the same work.
3. It prints one JSON object: `ai`, `session`, `entries` (text, ts, status mark, fixes, advice bullets, `after`, error, off), the
   pattern lines, and `notice` (the first-run line below, or null).

Actions use the same script: `pane.py --enhance <key>` (the `e` button: `coach.spawn_key`) and `pane.py --install <slug>` (the skill
button: the existing `review.py --install` path). Copying needs no Python: the module calls `$.ui.copy({ text: after, surface })`.

### `hooks/coachline.tsx`

- Runs `pane.py` with `$.process.run([py, `${$.plugin.root}/scripts/pane.py`, "--json", "--session", id])`. `py` is found once per
  load: `python3`, else `python`.
- Refreshes on `session.start`, on each `prompt.submit` and `turn.complete`, and every 3 s while any entry is pending (a
  `$.clock` timer that stops when nothing is pending). The JSON goes into `$.state`, so a refresh redraws only the pane.
- Draws what `watch.py`'s card shows, within the viewport `e.viewport` gives:
  - the header line (`coachline · this thread · N prompts`, `● Claude on`),
  - the selected prompt (white), Improve (blue bullets), the enhanced prompt with a Copy button,
  - the patterns line (a button toggles the list), and the prompt list (each a button that selects it).
  - Buttons: Copy, Analyse, Patterns, Install skill. Keyboard focus belongs to the prompt; the pane is driven by mouse/press.

## Defaults

`coach.setting()` gains platform defaults. On macOS and Linux, a setting the user has never written reads as:

| Setting | macOS / Linux default | Windows default |
| --- | --- | --- |
| `panel_ai` (Claude analysis) | **on** | off (unchanged) |
| `auto_open_watch` (pane opens itself) | **on** | off (unchanged) |
| `discover` (web search for tools) | off | off |

A value the user wrote (`/coach panel-ai off`) always wins. `auto_rewrite`, the old name of `panel_ai`, is still honoured.

**First-run notice.** During the user's first three sessions with analysis on by default (session ids kept in `notice_sessions` in
config; never once the user has written `panel_ai` themselves), the pane shows one dim line: `Claude analysis is on: prompts are sent redacted through your subscription ·
/coach panel-ai off`.

**README.** The privacy section changes from "off until you turn it on" to "on by default on macOS and Linux, off on Windows", with
the off switches. "Private by default" leaves the feature list. The Install section drops the `/coach watch` and `panel-ai on`
steps for macOS and Linux.

## Errors

| Failure | What the user sees |
| --- | --- |
| Module does not load (older Claude Code, API change) | Nothing new. Command hooks, `/coach`, `/coach watch` and the Windows split work as today. |
| No Python found | Pane shows: `coachline needs Python 3.9+ · run /coach doctor` |
| `pane.py` exits non-zero or prints bad JSON | Pane keeps the last good state and shows the first line of stderr, plus `run /coach doctor` |
| `$.ui.copy` resolves `isCopied: false` | Pane message: `no clipboard here: select the text instead` |

## Testing

- Python (`unittest`, alongside the existing 153 tests):
  - `pane.py --json` against a fixture history: the forced session, the JSON shape, the notice rules;
  - `ui` state persisting across two ticks, so the same prompt is not queued twice;
  - autopilot skipped while `watch.alive` is fresh;
  - platform defaults: macOS/Linux on, Windows off, a written value wins;
  - `launch.py --auto` on darwin/linux inside tmux opens nothing; on Windows the plan is unchanged (the existing tests keep that).
- Module (`claude plugin test`, `hooks/*.test.ts`): it opens on `session.start`; it opens again on the first `prompt.submit` when not
  placed; nothing on Windows; nothing when `auto_open_watch` is false; nothing after a person's close; Copy calls `$.ui.copy` with
  `after`; the error line when `pane.py` fails (the process mocked).
- Manual, on this Mac: install from the marketplace (a local marketplace pointing at the branch), restart, check success criteria 1-4.

## Step 0: feasibility check (before any of the above)

A throwaway plugin in the scratchpad, installed through a local marketplace, then removed. It answers:

1. Does `claude plugin validate` accept a `hooks.json` that holds both `hooks` (command hooks) and `modules`?
2. Does a **marketplace-installed** plugin (not a dev folder) load its module and open a pane?

If either answer is no, stop and bring it back to the user before continuing.

## Out of scope

- Any change to the Windows path or Windows defaults.
- Rewriting `watch.py`'s terminal UI; it stays for `/coach watch`, tmux and Windows.
- Keyboard shortcuts inside the pane.
- New coaching features.
