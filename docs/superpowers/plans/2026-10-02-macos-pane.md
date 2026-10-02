# coachline native pane (macOS and Linux) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On macOS and Linux, coachline's panel appears inside Claude Code as a native pane with zero setup, while Windows keeps its existing Windows Terminal split unchanged.

**Architecture:** A TypeScript hooks module (`hooks/coachline.tsx`) opens a Claude Code pane and draws it; all coaching logic stays in Python. A new `scripts/pane.py` runs one tick of `watch.py`'s loop without drawing (build state, queue background analyses) and prints JSON, including `watch.card_lines()` rows the module draws as-is. Platform-aware defaults in `coach.py` turn Claude analysis and auto-open on for macOS and Linux only.

**Tech Stack:** Python 3.9+ stdlib (unittest); Claude Code 2.1.287+ function-hooks module (TSX, `claude-code` and `claude-code/testing`); `claude plugin validate` / `claude plugin test`.

**Spec:** `docs/superpowers/specs/2026-10-02-macos-pane-design.md`

## Global Constraints

- Windows behaviour does not change: the `wt.exe` branch of `launch.plan()`, its opt-in auto-open, and Windows defaults (`panel_ai` off, `auto_open_watch` off) stay as they are.
- macOS / Linux defaults when the user never wrote the setting: `panel_ai` on, `auto_open_watch` on, `discover` off. A value the user wrote always wins; `auto_rewrite` (old name of `panel_ai`) is still honoured.
- Pane id is `coachline`, title `coachline`. Module does nothing when `$.env.get('OS') === 'Windows_NT'`, when the session is not interactive (`claude -p`, SDK), when auto-open is off, or after the person closed the pane by hand this session.
- First-run notice text, exactly: `Claude analysis is on: prompts are sent redacted through your subscription · /coach panel-ai off`. Shown during the first three sessions with analysis on by default; never once the user wrote `panel_ai`.
- Error lines, exactly: no Python → `coachline needs Python 3.9+ · run /coach doctor`; copy failed → `no clipboard here: select the text instead`.
- Python stays stdlib-only and must run on 3.9. Python tests run with `python3 -W error::ResourceWarning -m unittest discover -s tests` from the repo root.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Headless sessions** — coachline's own background analysis runs `claude -p`, which loads this plugin too. A non-interactive session must never run `pane.py` (that would queue analyses from inside analyses) and never open a pane. Test in Task 5 (`skips headless sessions`).
2. **Two ticks in quick succession** — `prompt.submit` and `turn.complete` both refresh; each tick is a new process. The same prompt must be queued once, not twice. Test in Task 3 (`test_a_second_tick_does_not_queue_the_same_prompt_again`).
3. **Standalone panel also open** — a user running `/coach watch` beside the pane must not get two autopilots. Test in Task 3 (`test_no_autopilot_while_a_standalone_panel_is_open`).
4. **Brand-new session, no prompts in history yet** — the session id the module passes is not in `history.jsonl`. `pane.py` must return an empty `entries` list, not fall back to another session's prompts and not crash. Test in Task 3 (`test_a_new_session_with_no_prompts_is_empty`).
5. **`pane.py` fails or prints garbage** — the pane must keep the last good state and show the error line, not go blank. Test in Task 5 (`keeps the last good state when pane.py fails`).

---

## File Map

| File | Change | Responsibility |
| --- | --- | --- |
| `scripts/coach.py` | modify | `defaults_on()`, `auto_open_on()`; `ai_on()` uses platform defaults; doctor line |
| `scripts/setup.py` | modify | settings display uses `auto_open_on()` |
| `scripts/launch.py` | modify | `--auto` never splits outside Windows |
| `scripts/watch.py` | modify | `build(path, session=None)` |
| `scripts/pane.py` | create | one tick as JSON; `--enhance`, `--install` actions |
| `hooks/hooks.json` | modify | add `"modules": ["./coachline.tsx"]` |
| `hooks/coachline.tsx` | create | open, refresh, draw, buttons |
| `hooks/coachline.test.ts` | create | module tests (`claude plugin test`) |
| `types/index.d.ts` | create | `$.state` contract |
| `.claude-plugin/plugin.json` | modify | `"types"`, version `0.13.0` |
| `tests/test_defaults.py`, `tests/test_pane.py` | create | Python tests |
| `tests/test_watch.py`, `tests/test_coachline.py`, `tests/test_panel_ai.py` | modify | pin legacy tests to Windows defaults |
| `README.md`, `skills/coach/SKILL.md` | modify | defaults, privacy, install |

---

### Task 1: Platform-aware defaults

**Files:**
- Modify: `scripts/coach.py` (imports line 1-9; `ai_on` at 327-330; doctor line 465)
- Modify: `scripts/setup.py:107` (the `auto-open` display line)
- Modify: `tests/test_watch.py`, `tests/test_coachline.py`, `tests/test_panel_ai.py` (top of file)
- Create: `tests/test_defaults.py`

**Interfaces:**
- Produces: `coach.defaults_on() -> bool`, `coach.auto_open_on() -> bool`, `coach.ai_on() -> bool` (now platform-aware). Env var `COACHLINE_PLATFORM` overrides `platform.system()` (tests only).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_defaults.py`:

```python
import json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach  # noqa: E402


class Defaults(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = coach.USER_CFG
        coach.USER_CFG = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        coach.USER_CFG = self.saved; self.tmp.cleanup()

    def on(self, system):
        return mock.patch.dict(os.environ, {"COACHLINE_PLATFORM": system})

    def write(self, **kw):
        with open(coach.USER_CFG, "w") as f: json.dump(kw, f)

    def test_macos_and_linux_turn_analysis_and_the_pane_on_by_default(self):
        for system in ("Darwin", "Linux"):
            with self.on(system):
                self.assertTrue(coach.ai_on(), system)
                self.assertTrue(coach.auto_open_on(), system)

    def test_windows_keeps_both_opt_in(self):
        with self.on("Windows"):
            self.assertFalse(coach.ai_on())
            self.assertFalse(coach.auto_open_on())

    def test_a_value_the_user_wrote_always_wins(self):
        self.write(panel_ai=False, auto_open_watch=False)
        with self.on("Darwin"):
            self.assertFalse(coach.ai_on()); self.assertFalse(coach.auto_open_on())
        self.write(panel_ai=True, auto_open_watch=True)
        with self.on("Windows"):
            self.assertTrue(coach.ai_on()); self.assertTrue(coach.auto_open_on())

    def test_the_old_auto_rewrite_name_is_still_honoured(self):
        self.write(auto_rewrite=False)
        with self.on("Darwin"): self.assertFalse(coach.ai_on())
        self.write(auto_rewrite=True)
        with self.on("Windows"): self.assertTrue(coach.ai_on())

    def test_discover_stays_off_everywhere(self):
        for system in ("Darwin", "Linux", "Windows"):
            with self.on(system): self.assertFalse(coach.setting("discover", False))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m unittest tests.test_defaults -v` (from repo root, with `tests` importable: use `python3 -m unittest discover -s tests -p test_defaults.py -v`)
Expected: FAIL / ERROR — `AttributeError: module 'coach' has no attribute 'auto_open_on'`, and `test_macos...` fails on `ai_on()`.

- [ ] **Step 3: Implement**

In `scripts/coach.py`, add `platform` to the import line:

```python
import argparse, collections, datetime as dt, json, os, platform, re, shutil, subprocess, sys, tempfile, time
```

Replace `ai_on()` (lines 327-330) with:

```python
def defaults_on():
    """macOS and Linux: Claude analysis and the pane are on until the user turns them off. Windows keeps them opt-in.
    COACHLINE_PLATFORM overrides the system name (tests)."""
    return (os.environ.get("COACHLINE_PLATFORM") or platform.system()) != "Windows"

def ai_on():
    """Claude analysis (advice per prompt, review of your history). 'auto_rewrite' is the old name of the same switch."""
    v = setting("panel_ai")
    if v is None: v = setting("auto_rewrite")
    return bool(defaults_on() if v is None else v)

def auto_open_on():
    """The panel opens by itself at session start: the Claude Code pane on macOS / Linux, a Windows Terminal split on Windows."""
    v = setting("auto_open_watch")
    return bool(defaults_on() if v is None else v)
```

In `doctor()` (line 465) replace `setting("auto_open_watch", False)` with `auto_open_on()`.

In `scripts/setup.py:107` replace `coach.setting('auto_open_watch', False)` with `coach.auto_open_on()`.

- [ ] **Step 4: Pin the legacy tests to Windows defaults**

These seven tests were written when analysis was opt-in everywhere (`test_watch.Colours` ×2, `test_watch.Patterns`, `test_watch.Status`, `test_coachline.Scripts.test_setup_without_options...`, `test_panel_ai.Autopilot.test_it_does_nothing...`, `test_panel_ai.EndToEnd.test_panel_status...`). Add, right after the `import` lines at the top of `tests/test_watch.py`, `tests/test_coachline.py` and `tests/test_panel_ai.py`:

```python
os.environ["COACHLINE_PLATFORM"] = "Windows"   # these tests pin the opt-in defaults; tests/test_defaults.py covers macOS and Linux
```

(Subprocesses inherit `os.environ`, so `watch.py --once` runs in those tests see it too.) `tests/test_defaults.py` patches the variable per test, so the order tests run in does not matter.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -W error::ResourceWarning -m unittest discover -s tests`
Expected: `OK (skipped=1)`, 158 tests.

- [ ] **Step 6: Commit**

```bash
git add scripts/coach.py scripts/setup.py tests/
git commit -m "feat: Claude analysis and auto-open on by default on macOS and Linux

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `launch.py --auto` never splits outside Windows; `watch.build` takes a session

**Files:**
- Modify: `scripts/launch.py:77` (the `auto` early return in `main`)
- Modify: `scripts/watch.py:182-188` (`build`)
- Test: `tests/test_launch.py`, `tests/test_watch.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `watch.build(path, session=None) -> dict`; when `session` is given, `st["session"] == session` and only that session's prompts are entries.

- [ ] **Step 1: Write the failing tests**

Append to class `Main` in `tests/test_launch.py` (it already redirects `coach.STATE` / `USER_CFG` in `setUp`; follow how its other tests call `launch.main(..., system=..., env=..., opener=..., which=...)` and read `self.opened`):

```python
    def test_auto_never_splits_outside_windows_the_claude_code_pane_does_it(self):
        coach.set_setting("auto_open_watch", True)
        for system in ("Darwin", "Linux"):
            rc = launch.main(["--auto"], system=system, env={"TMUX": "x"}, opener=self.opened.append, which=HAVE)
            self.assertEqual(rc, 0)
        self.assertEqual(self.opened, [])

    def test_auto_on_windows_still_splits_when_turned_on(self):
        coach.set_setting("auto_open_watch", True)
        launch.main(["--auto"], system="Windows", env={"WT_SESSION": "abc"}, opener=self.opened.append, which=lambda x: "wt.exe")
        self.assertEqual(self.opened[0][:4], ["wt.exe", "-w", "0", "split-pane"])
```

Append to `tests/test_watch.py` (uses the module's `history()` helper; `coach.HIST` is derived from `CLAUDE_CONFIG_DIR`, so call `watch.build` on the file path directly):

```python
class ForcedSession(unittest.TestCase):
    def test_build_shows_only_the_session_it_is_given(self):
        with tempfile.TemporaryDirectory() as cfg:
            history(cfg, [("s1", "p", VAGUE), ("s2", "p", SOLID)])
            st = watch.build(os.path.join(cfg, "history.jsonl"), session="s1")
            self.assertEqual(st["session"], "s1")
            self.assertEqual([e["text"] for e in st["entries"]], [VAGUE])

    def test_a_session_with_no_prompts_yet_has_no_entries(self):
        with tempfile.TemporaryDirectory() as cfg:
            history(cfg, [("s1", "p", VAGUE)])
            st = watch.build(os.path.join(cfg, "history.jsonl"), session="brand-new")
            self.assertEqual(st["entries"], [])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m unittest discover -s tests -p "test_launch.py" -v` and `-p "test_watch.py"`
Expected: the Darwin/Linux test fails (tmux split appended); `build()` raises `TypeError: unexpected keyword argument 'session'`.

- [ ] **Step 3: Implement**

`scripts/launch.py`, insert one line directly above line 77 and leave line 77 itself unchanged (it keeps reading `auto_open_watch` with a `False` default, which is exactly the Windows default; using `coach.auto_open_on()` there would read the real OS instead of the `system` argument and break the existing Windows tests on a Mac):

```python
    if auto and (system or platform.system()) != "Windows": return 0     # macOS / Linux: hooks/coachline.tsx opens a Claude Code pane instead
    if auto and not coach.setting("auto_open_watch", False): return 0    # unchanged
```

`scripts/watch.py`, change `build`'s signature, docstring and the session line:

```python
def build(path, session=None):
    """State for render(): THIS thread's prompts (the session you are in, see current_session, or `session` when the caller knows it,
    as the Claude Code pane does) plus what Claude knows from the rest."""
```

and replace `cur = st["session"] = current_session(rows); prev = None` with:

```python
    cur = st["session"] = session or current_session(rows); prev = None
```

Also move the `if not rows: return st` line so a given `session` is still reported: replace

```python
    if not rows: return st
```

with

```python
    if not rows: st["session"] = session; return st
```

- [ ] **Step 4: Run the whole suite**

Run: `python3 -W error::ResourceWarning -m unittest discover -s tests`
Expected: `OK (skipped=1)`.

- [ ] **Step 5: Commit**

```bash
git add scripts/launch.py scripts/watch.py tests/test_launch.py tests/test_watch.py
git commit -m "feat: session start splits only on Windows; build() takes the session it is shown

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `scripts/pane.py --json` (one tick)

**Files:**
- Create: `scripts/pane.py`
- Test: `tests/test_pane.py`

**Interfaces:**
- Consumes: `watch.build(path, session)`, `watch.new_ui()`, `watch.autopilot(st, ui, io=None, now=None)`, `watch.status(e, st, ui)`, `watch.card_lines(st, ui, i, e, iw)`, `watch.pattern_texts(st)`, `watch.stamp(ts)`, `watch.MAX_WIDTH`, `coach.ai_on()`, `coach.auto_open_on()`, `coach.panel_alive()`, `coach.setting/set_setting`, `coach.HIST`, `coach.STATE`.
- Produces: `pane.tick(session, width=80, io=None, now=None) -> dict` and CLI `python pane.py --json --session ID [--width N]` printing that dict as JSON. Shape (the module's `PaneState`, Task 5):

```json
{"ai": true, "auto_open": true, "session": "s1",
 "entries": [{"key": "...", "stamp": "15:28", "glyph": "✓", "state": "done", "words": "analysed",
              "text": "full redacted prompt", "after": "enhanced prompt or empty",
              "lines": [["prompt", "head", "Your prompt", "15:28 · ✓ analysed", null], ...]}],
 "patterns": ["You have asked for ..."], "skill": "slug-or-null", "notice": "text-or-null"}
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pane.py`:

```python
import json, os, subprocess, sys, tempfile, time, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import coach, pane  # noqa: E402
from test_watch import history, VAGUE, SOLID  # noqa: E402

NOTICE = "Claude analysis is on: prompts are sent redacted through your subscription · /coach panel-ai off"


class FakeIO:
    def __init__(self): self.enhanced, self.reviews = [], 0
    def enhance(self, key): self.enhanced.append(key)
    def review(self): self.reviews += 1


class Tick(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); c = self.cfg = self.tmp.name
        self.saved = (coach.CONFIG, coach.HIST, coach.STATE, coach.USER_CFG, coach.ALIVE, coach.REWRITES, coach.LEARNED, coach.REVIEW_LOCK)
        coach.CONFIG, coach.HIST, coach.STATE = c, os.path.join(c, "history.jsonl"), os.path.join(c, "coach")
        coach.USER_CFG, coach.ALIVE = os.path.join(coach.STATE, "config.json"), os.path.join(coach.STATE, "watch.alive")
        coach.REWRITES, coach.LEARNED = os.path.join(coach.STATE, "rewrites.jsonl"), os.path.join(coach.STATE, "learned.json")
        coach.REVIEW_LOCK = os.path.join(coach.STATE, "review.running")
        os.makedirs(coach.STATE)
        self.env = mock.patch.dict(os.environ, {"COACHLINE_PLATFORM": "Darwin"}); self.env.start()
        self.io = FakeIO()

    def tearDown(self):
        self.env.stop()
        (coach.CONFIG, coach.HIST, coach.STATE, coach.USER_CFG, coach.ALIVE, coach.REWRITES, coach.LEARNED, coach.REVIEW_LOCK) = self.saved
        self.tmp.cleanup()

    def tick(self, session="s1", now=None):
        return pane.tick(session, width=80, io=self.io, now=now)

    def test_it_returns_only_this_sessions_prompts_with_card_lines(self):
        history(self.cfg, [("s1", "p", VAGUE), ("s2", "p", SOLID)])
        st = self.tick()
        self.assertEqual(st["session"], "s1")
        self.assertEqual([e["text"] for e in st["entries"]], [VAGUE])
        lines = st["entries"][0]["lines"]
        self.assertEqual(lines[0][:3], ["prompt", "head", "Your prompt"])
        self.assertTrue(all(len(l) == 5 for l in lines))
        json.dumps(st)                                                     # it must be JSON-safe

    def test_a_new_session_with_no_prompts_is_empty(self):
        history(self.cfg, [("old", "p", VAGUE)])
        st = self.tick("brand-new")
        self.assertEqual(st["entries"], [])
        self.assertEqual(self.io.enhanced, [])

    def test_it_queues_the_newest_unanalysed_prompt_when_analysis_is_on(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        st = self.tick()
        self.assertEqual(len(self.io.enhanced), 1)
        self.assertEqual(st["entries"][0]["state"], "pending")

    def test_a_second_tick_does_not_queue_the_same_prompt_again(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        t = time.time()
        self.tick(now=t); self.tick(now=t + 3)
        self.assertEqual(len(self.io.enhanced), 1)

    def test_no_autopilot_while_a_standalone_panel_is_open(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        open(coach.ALIVE, "w").close()
        self.tick()
        self.assertEqual(self.io.enhanced, [])

    def test_nothing_is_queued_when_the_user_turned_analysis_off(self):
        coach.set_setting("panel_ai", False)
        history(self.cfg, [("s1", "p", VAGUE)])
        st = self.tick()
        self.assertEqual(self.io.enhanced, []); self.assertFalse(st["ai"])

    def test_the_notice_shows_in_the_first_three_sessions_only(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        for sid in ("a", "b", "c"):
            self.assertEqual(self.tick(sid)["notice"], NOTICE)
            self.assertEqual(self.tick(sid)["notice"], NOTICE)           # still shown on the next tick of the same session
        self.assertIsNone(self.tick("d")["notice"])

    def test_no_notice_once_the_user_chose(self):
        coach.set_setting("panel_ai", True)
        self.assertIsNone(self.tick()["notice"])

    def test_the_cli_prints_json(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        coach.set_setting("panel_ai", False)                              # the subprocess must not spawn a real `claude`
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.cfg, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "pane.py"), "--json", "--session", "s1", "--width", "60"],
                           capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["entries"][0]["text"], VAGUE)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m unittest discover -s tests -p "test_pane.py" -v`
Expected: ERROR — `ModuleNotFoundError: No module named 'pane'`.

- [ ] **Step 3: Implement `scripts/pane.py`**

```python
"""pane.py - the coachline panel for Claude Code's own pane (hooks/coachline.tsx): one tick, no drawing.

  python pane.py --json --session ID [--width N]   this thread's state as JSON; queues Claude's analysis when it is on
  python pane.py --enhance KEY                     ask Claude about one prompt now (the pane's Analyse button)
  python pane.py --install SLUG                    install a skill Claude drafted (the pane's Install button)

Each call is a fresh process, so what watch.py keeps in memory between frames (which prompts were sent, when the history review is
next due) is kept in ~/.claude/coach/pane-<session>.json. When a standalone panel (watch.py) is open, it does the background work.
"""
import argparse, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach, review, watch

NOTICE = "Claude analysis is on: prompts are sent redacted through your subscription · /coach panel-ai off"
NOTICE_SESSIONS = 3


def ui_path(session):
    return os.path.join(coach.STATE, "pane-" + (re.sub(r"[^0-9A-Za-z-]", "", session or "")[:64] or "none") + ".json")


def load_ui(session):
    ui = watch.new_ui()
    try:
        with open(ui_path(session), encoding="utf-8") as f: d = json.load(f)
        ui["pending"] = {str(k): float(t) for k, t in d.get("pending", {}).items()}
        ui["tried"] = set(map(str, d.get("tried", [])))
        ui["review_after"] = float(d.get("review_after", 0.0))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return ui


def save_ui(session, ui):
    try:
        os.makedirs(coach.STATE, exist_ok=True)
        with open(ui_path(session), "w", encoding="utf-8") as f:
            json.dump({"pending": ui["pending"], "tried": sorted(ui["tried"]), "review_after": ui["review_after"]}, f)
    except OSError:
        pass


def notice(session, ai):
    """The first-run line: only while analysis is on because of the default (the user never chose), in their first three sessions."""
    if not ai or coach.setting("panel_ai") is not None or coach.setting("auto_rewrite") is not None: return None
    seen = coach.setting("notice_sessions", [])
    if not isinstance(seen, list): seen = []
    if session in seen: return NOTICE
    if len(seen) >= NOTICE_SESSIONS: return None
    coach.set_setting("notice_sessions", seen + [session])
    return NOTICE


def tick(session, width=80, io=None, now=None):
    st = watch.build(coach.HIST, session=session)
    ui = load_ui(session)
    if not coach.panel_alive(): watch.autopilot(st, ui, io=io, now=now)
    save_ui(session, ui)
    iw = max(20, min(width, watch.MAX_WIDTH) - 4)
    entries = []
    for i, e in enumerate(st["entries"]):
        state, glyph, _kind, words = watch.status(e, st, ui)
        entries.append({"key": e["key"], "stamp": watch.stamp(e["ts"]), "glyph": glyph, "state": state, "words": words,
                        "text": e["text"], "after": e["after"], "lines": [list(l) for l in watch.card_lines(st, ui, i, e, iw)]})
    skill = next((x["slug"] for x in st["insights"] if x.get("slug")), None)
    return {"ai": st["ai"], "auto_open": coach.auto_open_on(), "session": st["session"], "entries": entries,
            "patterns": watch.pattern_texts(st), "skill": skill, "notice": notice(session, st["ai"])}


def main(argv):
    ap = argparse.ArgumentParser(description="coachline panel state for the Claude Code pane")
    ap.add_argument("--json", action="store_true"); ap.add_argument("--session"); ap.add_argument("--width", type=int, default=80)
    ap.add_argument("--enhance", metavar="KEY"); ap.add_argument("--install", metavar="SLUG")
    a = ap.parse_args(argv)
    if a.enhance:
        coach.spawn_key(a.enhance); print("asking Claude in the background (about 20 seconds)"); return 0
    if a.install:
        ok, msg = review.install_skill(a.install); print(msg); return 0 if ok else 1
    if a.json and a.session:
        sys.stdout.write(json.dumps(tick(a.session, a.width), ensure_ascii=False)); return 0
    ap.print_help(); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest discover -s tests -p "test_pane.py" -v`
Expected: all PASS. If `test_a_second_tick...` fails, check that `save_ui` writes `tried` and `pending` and that `autopilot` reads `ui["pending"]` within `PENDING_SECONDS`.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -W error::ResourceWarning -m unittest discover -s tests`
Expected: `OK (skipped=1)`.

- [ ] **Step 6: Commit**

```bash
git add scripts/pane.py tests/test_pane.py
git commit -m "feat: pane.py, one tick of the panel as JSON for the Claude Code pane

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `pane.py` actions (`--enhance`, `--install`)

**Files:**
- Test: `tests/test_pane.py` (the code is already in Task 3's `main`; this task pins it)

**Interfaces:**
- Produces: `pane.main(["--enhance", KEY]) -> 0` (calls `coach.spawn_key(KEY)`); `pane.main(["--install", SLUG]) -> 0|1` printing `review.install_skill`'s message.

- [ ] **Step 1: Write the tests**

Append to `tests/test_pane.py`:

```python
class Actions(unittest.TestCase):
    def test_enhance_starts_one_background_analysis(self):
        with mock.patch.object(coach, "spawn_key") as spawn:
            self.assertEqual(pane.main(["--enhance", "123.0:abc"]), 0)
        spawn.assert_called_once_with("123.0:abc")

    def test_install_reports_what_happened(self):
        with mock.patch.object(pane.review, "install_skill", return_value=(False, "no draft at x; run the review first")):
            with mock.patch("sys.stdout") as out:
                self.assertEqual(pane.main(["--install", "write-commit"]), 1)
        self.assertIn("no draft", "".join(c.args[0] for c in out.write.call_args_list))

    def test_no_arguments_is_an_error_not_a_crash(self):
        with mock.patch("sys.stdout"):
            self.assertEqual(pane.main([]), 2)
```

- [ ] **Step 2: Run them**

Run: `python3 -m unittest discover -s tests -p "test_pane.py" -v`
Expected: PASS (the behaviour shipped in Task 3). If any fails, fix `pane.main` to match the Interfaces line above.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pane.py
git commit -m "test: pane.py actions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The hooks module (`hooks/coachline.tsx`)

**Files:**
- Modify: `hooks/hooks.json`, `.claude-plugin/plugin.json`
- Create: `types/index.d.ts`, `hooks/coachline.tsx`, `hooks/coachline.test.ts`

**Interfaces:**
- Consumes: `pane.py --json --session ID --width N` (Task 3 JSON shape), `pane.py --enhance KEY`, `pane.py --install SLUG` (Task 4).
- Produces: pane id `coachline`; `$.state` keys under plugin `coachline`: `state`, `error`, `sel`, `full`, `showPatterns`, `closed`, `msg`.

API facts (Claude Code 2.1.287; the authority is the types file the `plugin-authoring` skill names — grep it when unsure):
- `$.ui.open({ id, title })` from `session.start` is placed from 144 columns; from a `prompt.submit` hook it counts as asked and is placed at any width.
- `$.session.id()`, `$.env.get(name)`, `$.plugin.root` (a string), `$.process.run(argv, { timeoutMs })` → `{ exitCode, stdout, stderr, isStdoutTruncated, isStderrTruncated }`, `$.clock.every(ms, fn)` → `{ cancel }`, `$.ui.panes()` → `[{ id, isPlaced, ... }]`, `$.ui.copy({ text, surface })` → `{ isCopied }`.
- `ui.close` input: `{ id, origin: 'plugin' | 'person' | 'unload' }`. `session.start` input: `{ cwd, surface, isInteractive }`.
- In `claude plugin test`, every `$` call the module makes must be answered by a test hook (the bottom hook throws, naming the event).

- [ ] **Step 1: Manifest, hooks.json and the state contract**

`hooks/hooks.json` — keep the existing `"hooks"` object exactly; add a sibling key:

```json
  "modules": ["./coachline.tsx"]
```

`.claude-plugin/plugin.json` — add `"types": "./types/index.d.ts"` and set `"version": "0.13.0"`.

Create `types/index.d.ts`:

```ts
export type PaneLine = [section: string, kind: string, text: string, right: string, action: string | null]

export type PaneEntry = {
  key: string
  stamp: string
  glyph: string
  state: string
  words: string
  text: string
  after: string
  lines: PaneLine[]
}

export type PaneState = {
  ai: boolean
  auto_open: boolean
  session: string | null
  entries: PaneEntry[]
  patterns: string[]
  skill: string | null
  notice: string | null
}

declare module 'claude-code' {
  interface PluginState {
    coachline: {
      state: PaneState | null
      error: string
      sel: number
      full: boolean
      showPatterns: boolean
      closed: boolean
      msg: string
    }
  }
}
```

- [ ] **Step 2: Write the failing module tests**

Create `hooks/coachline.test.ts`:

```ts
import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const STATE = (over = {}) =>
  JSON.stringify({ ai: true, auto_open: true, session: 's1', entries: [], patterns: [], skill: null, notice: null, ...over })

function world(on: On, opts: { os?: string; out?: string; exit?: number } = {}) {
  const opened: string[] = []
  const ran: string[][] = []
  mock.env(on, opts.os ? { OS: opts.os } : {})
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('prompt.submit', ($, e) => ({ text: e.text }))
  on('turn.complete', () => ({ text: '' }))
  on('session.id', () => 's1')
  on('ui.panes', () => [])
  on('ui.open', ($, e) => {
    opened.push(e.id)
    return { isPlaced: true }
  })
  on('process.run', ($, e) => {
    ran.push([...e.argv])
    const version = e.argv.includes('--version')
    return {
      exitCode: version ? 0 : (opts.exit ?? 0),
      stdout: version ? 'Python 3.13.0' : (opts.out ?? STATE()),
      stderr: opts.exit ? 'Traceback\nboom' : '',
      isStdoutTruncated: false,
      isStderrTruncated: false,
    }
  })
  return { opened, ran }
}

const START = { cwd: '/w', surface: 'terminal', isInteractive: true } as const

test('opens the pane at session start on macOS', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  expect(w.opened).toEqual(['coachline'])
  expect(w.ran.some(a => a.includes('--json') && a.includes('s1'))).toBe(true)
})

test('does nothing on Windows', async ($, on) => {
  const w = world(on, { os: 'Windows_NT' })
  await $.session.start(START)
  await $.prompt.submit({ text: 'hi', wait: false })
  expect(w.opened).toEqual([])
  expect(w.ran).toEqual([])
})

test('skips headless sessions', async ($, on) => {
  const w = world(on)
  await $.session.start({ ...START, surface: null, isInteractive: false })
  await $.prompt.submit({ text: 'hi', wait: false })
  expect(w.opened).toEqual([])
  expect(w.ran).toEqual([])
})

test('does not open when auto-open is off', async ($, on) => {
  const w = world(on, { out: STATE({ auto_open: false }) })
  await $.session.start(START)
  await $.prompt.submit({ text: 'hi', wait: false })
  expect(w.opened).toEqual([])
})

test('opens again on a prompt while the pane is not placed', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit({ text: 'hi', wait: false })
  expect(w.opened).toEqual(['coachline', 'coachline'])
})

test('stays closed after the person closes it', async ($, on) => {
  const w = world(on)
  on('ui.close', () => undefined)
  await $.session.start(START)
  await $.ui.close({ id: 'coachline', origin: 'person' })
  await $.prompt.submit({ text: 'hi', wait: false })
  expect(w.opened).toEqual(['coachline'])
})

test('keeps the last good state when pane.py fails', async ($, on) => {
  let exit = 0
  const opened: string[] = []
  mock.env(on, {})
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('prompt.submit', ($, e) => ({ text: e.text }))
  on('session.id', () => 's1')
  on('ui.panes', () => [{ id: 'coachline', title: 'coachline', isShown: true, isFocused: false, isPlaced: true }])
  on('ui.open', ($, e) => { opened.push(e.id); return { isPlaced: true } })
  on('process.run', ($, e) => ({
    exitCode: e.argv.includes('--version') ? 0 : exit,
    stdout: e.argv.includes('--version') ? 'Python 3.13.0' : STATE({ entries: [] }),
    stderr: exit ? 'Traceback\nboom' : '',
    isStdoutTruncated: false,
    isStderrTruncated: false,
  }))
  await $.session.start(START)
  exit = 1
  await $.prompt.submit({ text: 'hi', wait: false })
  const s = await $.state.get({ plugin: 'coachline', key: 'state' } as const)
  const err = await $.state.get({ plugin: 'coachline', key: 'error' } as const)
  expect(s.value?.session).toBe('s1')
  expect(err.value).toContain('run /coach doctor')
})
```

Notes for the implementer: if a call signature in these tests (`$.prompt.submit`, `$.ui.close`, `$.state.get`) differs on this build, grep the types file for `'prompt.submit'`, `'ui.close'`, `export type Engine` and adjust the test, not the intent.

- [ ] **Step 3: Run them to verify they fail**

Run: `claude plugin test /Users/teransarathchandra/Development/coachline`
Expected: FAIL — the module `./coachline.tsx` does not exist.

- [ ] **Step 4: Implement `hooks/coachline.tsx`**

```tsx
import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { PaneEntry, PaneLine, PaneState } from '../types'

const PANE = 'coachline'
const NO_PYTHON = 'coachline needs Python 3.9+ · run /coach doctor'
const NO_CLIPBOARD = 'no clipboard here: select the text instead'

const state = atom({ plugin: 'coachline', key: 'state' } as const, null as PaneState | null)
const error = atom({ plugin: 'coachline', key: 'error' } as const, '')
const sel = atom({ plugin: 'coachline', key: 'sel' } as const, -1)
const full = atom({ plugin: 'coachline', key: 'full' } as const, false)
const showPatterns = atom({ plugin: 'coachline', key: 'showPatterns' } as const, false)
const closed = atom({ plugin: 'coachline', key: 'closed' } as const, false)
const msg = atom({ plugin: 'coachline', key: 'msg' } as const, '')

// watch.py's colours, by line kind (see CODE in scripts/watch.py)
const COLOR: Record<string, string> = {
  prompt: 'whiteBright', blue: 'blueBright', bluedim: 'blueBright', enh: 'blueBright', task: 'blueBright', meta: 'gray',
}
const HEAD_COLOR: Record<string, string> = { prompt: 'whiteBright', improve: 'blueBright', enh: 'blueBright', info: 'blueBright', web: 'green' }

type Run = { ok: true; out: string } | { ok: false; err: string }

export const register: Register = on => {
  let active = false          // an interactive session on macOS / Linux; false under `claude -p`, the SDK and on Windows
  let py: string | null = null
  let width = 80
  let poll: { cancel: () => void } | null = null

  async function python($: Parameters<Parameters<typeof on>[1]>[0]): Promise<string | null> {
    if (py) return py
    for (const name of ['python3', 'python']) {
      try {
        const r = await $.process.run([name, '--version'], { timeoutMs: 5000 })
        if (r.exitCode === 0) return (py = name)
      } catch {
        // not on PATH: try the next name
      }
    }
    return null
  }

  async function run($: any, args: string[]): Promise<Run> {
    const p = await python($)
    if (!p) return { ok: false, err: NO_PYTHON }
    try {
      const r = await $.process.run([p, `${$.plugin.root}/scripts/pane.py`, ...args], { timeoutMs: 20000 })
      if (r.exitCode !== 0) {
        const last = r.stderr.trim().split('\n').pop() || `pane.py exited ${r.exitCode}`
        return { ok: false, err: `coachline: ${last} · run /coach doctor` }
      }
      return { ok: true, out: r.stdout }
    } catch (x) {
      return { ok: false, err: `coachline: ${String(x)} · run /coach doctor` }
    }
  }

  async function refresh($: any): Promise<PaneState | null> {
    const r = await run($, ['--json', '--session', await $.session.id(), '--width', String(width)])
    let s: PaneState | null = null
    if (r.ok) {
      try {
        s = JSON.parse(r.out) as PaneState
      } catch {
        await update($, error, () => 'coachline: pane.py gave a bad answer · run /coach doctor')
        return null
      }
    } else {
      await update($, error, () => r.err)       // the last good state stays
      return null
    }
    await update($, error, () => '')
    await update($, state, () => s)
    const busy = s.entries.some(e => e.state === 'pending')
    if (busy && !poll) poll = $.clock.every(3000, () => void refresh($))
    if (!busy && poll) {
      poll.cancel()
      poll = null
    }
    return s
  }

  async function open($: any): Promise<void> {
    if (await read($, closed)) return
    const panes = await $.ui.panes()
    if (panes.some((p: { id: string; isPlaced: boolean }) => p.id === PANE && p.isPlaced)) return
    await $.ui.open({ id: PANE, title: 'coachline' })
  }

  on('session.start', async ($, e, next) => {
    const r = await next(e)
    active = e.isInteractive && (await $.env.get('OS')) !== 'Windows_NT'
    if (!active) return r
    const s = await refresh($)
    if (s?.auto_open) await open($)
    return r
  })

  on('prompt.submit', async ($, e, next) => {
    const r = await next(e)
    if (!active) return r
    const s = await refresh($)
    if (s?.auto_open) await open($)            // from a prompt the person entered: placed at any width
    await update($, sel, () => -1)             // follow the newest prompt
    return r
  })

  on('turn.complete', async ($, e, next) => {
    const r = await next(e)
    if (active) await refresh($)
    return r
  })

  on('ui.close', async ($, e, next) => {
    if (e.id === PANE && e.origin === 'person') await update($, closed, () => true)
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    width = e.viewport?.columns ?? width
    const s = await read($, state)
    const err = await read($, error)
    const note = await read($, msg)
    if (!s) return <Text dimColor>{err || 'coachline: loading…'}</Text>

    const header = (
      <Box key="header" justifyContent="space-between">
        <Text bold>coachline · this thread · {s.entries.length} prompt{s.entries.length === 1 ? '' : 's'}</Text>
        <Text color={s.ai ? 'green' : 'gray'}>{s.ai ? '● Claude on' : '○ Claude off'}</Text>
      </Box>
    )
    const footer = [
      err ? <Text key="err" color="red">{err}</Text> : null,
      note ? <Text key="msg" dimColor>{note}</Text> : null,
      s.notice ? <Text key="notice" dimColor>{s.notice}</Text> : null,
    ]
    if (!s.entries.length) {
      return (
        <Box flexDirection="column">
          {header}
          <Text dimColor>Send a prompt: coachline coaches it here.</Text>
          {footer}
        </Box>
      )
    }

    const at = await read($, sel)
    const i = at < 0 || at >= s.entries.length ? s.entries.length - 1 : at
    const cur: PaneEntry = s.entries[i]
    const isFull = await read($, full)
    const pats = await read($, showPatterns)

    const copy = async () => {
      const r = await $.ui.copy({ text: cur.after, surface: e.surface })
      await update($, msg, () => (r.isCopied ? `copied the enhanced prompt (${cur.after.length} characters)` : NO_CLIPBOARD))
    }
    const analyse = async () => {
      const r = await run($, ['--enhance', cur.key])
      await update($, msg, () => (r.ok ? r.out.trim() : r.err))
      await refresh($)
    }
    const install = async () => {
      if (!s.skill) return
      const r = await run($, ['--install', s.skill])
      await update($, msg, () => (r.ok ? r.out.trim() : r.err))
    }

    const line = (l: PaneLine, n: number) => {
      const [section, kind, text, right, action] = l
      if (kind === 'blank') return <Text key={`l${n}`}> </Text>
      if (kind === 'head') {
        return (
          <Box key={`l${n}`} justifyContent="space-between">
            <Text bold color={HEAD_COLOR[section] ?? 'blueBright'}>{text}</Text>
            {action === 'copy' ? <Button key="copy" label={right || 'Copy'} onPress={copy} />
              : action === 'enhance' ? <Button key="analyse" label="Analyse" onPress={analyse} />
              : right ? <Text dimColor>{right}</Text> : null}
          </Box>
        )
      }
      if (action === 'enter') return <Button key="whole" label="Show the whole prompt" onPress={() => update($, full, () => true)} />
      if (action === 'enhance') return <Button key={`an${n}`} label={text} onPress={analyse} />
      return <Text key={`l${n}`} color={COLOR[kind]} dimColor={kind === 'bluedim' || kind === 'meta'} bold={kind === 'prompt'}>{text}</Text>
    }

    const card = isFull
      ? [<Text key="fullhead" bold>Your prompt</Text>, <Text key="fulltext" color="whiteBright">{cur.text}</Text>,
         <Button key="less" label="Show less" onPress={() => update($, full, () => false)} />]
      : cur.lines.map(line)

    return (
      <Box flexDirection="column">
        {header}
        <Box flexDirection="column" marginY={1}>{card}</Box>
        {s.patterns.length > 0 && (
          <Box flexDirection="column">
            <Button key="patterns" label={pats ? 'Hide patterns' : `${s.patterns.length} pattern${s.patterns.length === 1 ? '' : 's'} from your past chats`}
              onPress={() => update($, showPatterns, v => !v)} />
            {pats && s.patterns.map((p, n) => <Text key={`p${n}`} color="blueBright">{p}</Text>)}
            {s.skill && <Button key="skill" label={`Install the drafted skill /${s.skill}`} onPress={install} />}
          </Box>
        )}
        <Text dimColor>Prompts in this thread</Text>
        {s.entries.map((x, n) => (
          <Button key={`e${n}`} label={`${n === i ? '›' : ' '} ${x.glyph} ${x.stamp}  ${x.text.replace(/\s+/g, ' ').slice(0, Math.max(10, width - 16))}`}
            onPress={() => update($, sel, () => n)} />
        ))}
        {footer}
      </Box>
    )
  })
}
```

Notes for the implementer:
- Replace the `any` / `Parameters<...>` annotations on `$` with the engine interface type the types file exports for a hook's `$` (grep `export type Register` and follow it), so `tsc` passes without `any`.
- If `Box` rejects `justifyContent` or `marginY` on the terminal surface, `claude plugin validate` names the prop; drop it rather than work around it.

- [ ] **Step 5: Validate, type-check and test**

Run: `claude plugin validate /Users/teransarathchandra/Development/coachline`
Expected: `✔ Validation passed` (the `author` warning, if any, is pre-existing). It must list `./coachline.tsx hooks: session.start, prompt.submit, turn.complete, ui.close, ui.render{component=Pane, requestId=coachline}`.

Run: `claude plugin test /Users/teransarathchandra/Development/coachline`
Expected: 7 tests pass.

Type-check: write a `tsconfig.json` outside the repo (in the scratchpad) per the header of the types file the `plugin-authoring` skill names, with `include` naming that file plus `hooks/*.tsx`, `hooks/*.ts` and `types/*.d.ts`, then run `npx -y -p typescript tsc -p <that tsconfig>`.
Expected: no errors.

- [ ] **Step 6: Run the Python suite (nothing there should change)**

Run: `python3 -W error::ResourceWarning -m unittest discover -s tests`
Expected: `OK (skipped=1)`.

- [ ] **Step 7: Commit**

```bash
git add hooks/ types/ .claude-plugin/plugin.json
git commit -m "feat: coachline opens as a Claude Code pane on macOS and Linux

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Docs (README, skill)

**Files:**
- Modify: `README.md`, `skills/coach/SKILL.md`

- [ ] **Step 1: README**

Make these edits:
- Features: replace `- **Private by default**: nothing is sent to Claude until you turn analysis on.` with `- **Opens by itself**: on macOS and Linux the panel appears inside Claude Code as soon as you start; nothing to set up.`
- Requirements: add `- Claude Code 2.1.287 or newer for the built-in pane (older versions: use /coach watch)`.
- Install, after "Restart Claude Code.": replace the block that follows with:

```
On macOS and Linux that is all: the panel opens inside Claude Code (from 144 columns at start, otherwise with your first prompt), and Claude analysis is on. Turn either off with `/coach auto-open off` or `/coach panel-ai off`.

On Windows, run `/coach panel-ai on` to let Claude analyse your prompts, and `/coach auto-open on` to open the panel in a Windows Terminal split on every session (or use the command from `/coach watch`).
```

- Privacy: replace the first bullet with `- Analysis is **on by default on macOS and Linux** and off on Windows. Turn it off with /coach panel-ai off; then only built-in local hints run, on your machine. The panel says so in your first three sessions.`
- Limits: replace the Auto-open bullet with `- The built-in pane needs Claude Code 2.1.287+. The Windows split was tested on Windows Terminal; /coach watch works in any terminal.`
- Commands table: change `/coach auto-open on|off` to `Open the panel by itself at session start (on by default on macOS and Linux)` and `/coach panel-ai on|off` to `Turn Claude analysis on or off (on by default on macOS and Linux)`.

- [ ] **Step 2: Skill**

In `skills/coach/SKILL.md`, in the `/coach auto-open` bullet replace `While on, starting a session splits a pane with the panel (tmux or Windows Terminal only; never a separate window).` with `While on, the panel opens by itself at session start: inside Claude Code on macOS and Linux (on by default), a Windows Terminal split on Windows.` In the `/coach panel-ai` bullet, add after its first sentence: `It is on by default on macOS and Linux.`

- [ ] **Step 3: Commit**

```bash
git add README.md skills/coach/SKILL.md
git commit -m "docs: the panel opens by itself on macOS and Linux; analysis on by default there

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Manual verification on macOS (as a fresh user)

**Files:** none changed.

- [ ] **Step 1: Install the branch through a local marketplace**

```bash
claude plugin uninstall coachline@coachline
claude plugin marketplace remove coachline
claude plugin marketplace add /Users/teransarathchandra/Development/coachline
claude plugin install coachline@coachline
mv ~/.claude/coach ~/.claude/coach.before-pane-test     # a fresh user has no state (restore it in Step 4)
```

- [ ] **Step 2: Ask the user to restart Claude Code in a terminal narrower than 144 columns, then in one wider**

Check against the spec's success criteria:
1. Narrow: nothing at start; after the first prompt, the pane appears showing that prompt.
2. Wide: the pane is there before any prompt, saying `Send a prompt: coachline coaches it here.`
3. Within ~30 s of a prompt, its card shows Improve and an Enhanced prompt; Copy puts it on the clipboard (`pbpaste`).
4. The notice line shows. `/coach panel-ai off` stops new analyses; `/coach auto-open off` + restart: no pane. Closing the pane by hand keeps it closed until the next session.
5. `claude -p "say ok"` from a terminal leaves no `pane-*.json` for its session in `~/.claude/coach/`.
6. Confirm the session id: the `session` in `~/.claude/coach/pane-<id>.json` filename matches the `sessionId` of the newest line in `~/.claude/history.jsonl`. If not, `$.session.id()` is not the history id: stop and report.

- [ ] **Step 3: Record results** in the PR description (each criterion: pass / fail, with what was seen).

- [ ] **Step 4: Restore**

```bash
rm -rf ~/.claude/coach && mv ~/.claude/coach.before-pane-test ~/.claude/coach
claude plugin uninstall coachline@coachline && claude plugin marketplace remove coachline
claude plugin marketplace add teransarathchandra/coachline && claude plugin install coachline@coachline
```
