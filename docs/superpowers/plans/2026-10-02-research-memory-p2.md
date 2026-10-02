# Research memory (P2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Research suggestions are remembered: each is shown with at most two prompts, the user can hide one or mark it as used, the enhanced prompt carries the verified links as a References block, and research can be re-run for one prompt on demand.

**Architecture:** A new `memory.py` keeps `<state>/suggestions.json`, reusing `discover._load`/`_dump`. The research queue (`discover._research`) picks up to 4 items through memory. `watch.build` drops hidden items, numbers the rest and appends `discover.references(...)` to the enhanced prompt at display time. The terminal panel gets `x`/`a`/`r`, and the Claude Code pane gets matching buttons through new `pane.py --mark/--research` calls.

**Tech Stack:** Python 3.9+ stdlib, `unittest`; the Claude Code hooks module `hooks/coachline.tsx` (tests: `claude plugin test .`).

**Spec:** `docs/superpowers/specs/2026-10-02-research-engine-design.md` (section "P2 scope")

## Global Constraints

- Branch `feat/research-memory`, stacked on `feat/research-engine` (PR #23). Rebase onto `main` if #23 merges first.
- Stdlib only; Python 3.9 compatible.
- Memory is local only: `<state>/suggestions.json` is never sent anywhere.
- At most 2 prompts per shown item (`memory.MAX_SHOWN = 2`); at most 4 shown per prompt (`discover.MAX_ITEMS`); research keeps up to 8 verified (`discover.MAX_RAW`); at most 500 unmarked items stored (`memory.MAX_KEEP`); statuses `dismissed`, `adopted`.
- References header, verbatim: `References (checked links from web research):`. Verbs: tool `Use`, tech `Consider`, docs `Follow`, inspo `Take visual cues from`.
- Card note, verbatim: `Includes references from web research: x hides one, a marks one you use, r looks again.`
- The footer key list (`watch.FOOT`) does not change.
- Forced research (`r`, Look again, `discover.py --key`) still never sends an `llm-off.txt` project.
- Model / web text reaching the terminal goes through `coach.clean` (already true for stored items).
- Python tests: `python3 -W error::ResourceWarning -m unittest discover -s tests`. Pane tests: `claude plugin test .`
- In-process tests patch `coach.STATE` (memory reads it at call time) and never touch the real `~/.claude/coach`.

## Review Focus

1. **A corrupt or hand-edited `suggestions.json`** (not JSON, items that aren't objects) must never break picking or the panel. Pinned in Task 1 (`test_a_broken_or_huge_file_never_breaks_picking`).
2. **Copying right after hiding an item** must not include the hidden link: the copy reads the rebuilt state. Pinned in Task 4 (`test_x_then_a_number_hides_that_suggestion_and_the_copy_follows`).
3. **Pressing `x` and then an unrelated key** must cancel, not hide a random item. Pinned in Task 4 (`test_any_other_key_cancels_the_choice`).
4. **Forced research (`--key`) on an `llm-off.txt` project or a prompt with no advice yet** must send nothing and say why. Pinned in Task 2 (`test_research_by_key_refuses_opted_out_and_unanalysed_prompts`).
5. **Records from P1** (discovery without ids, old kinds) must still show, numbered and with references. Pinned in Task 3 (`test_p1_records_still_show_with_references`).

---

### Task 1: `memory.py`

**Files:**
- Create: `scripts/memory.py`
- Test: `tests/test_memory.py`

**Interfaces:**
- Consumes: `discover._load(name) -> dict`, `discover._dump(name, d)`, `discover.MAX_ITEMS`.
- Produces: `memory.item_id(item) -> str`, `memory.pick(items, key=None, limit=discover.MAX_ITEMS) -> list`, `memory.mark(iid, status) -> bool`, `memory.statuses() -> {id: status}`, constants `MAX_SHOWN, MAX_KEEP, STATUSES`.

- [ ] **Step 1: Create the branch**

```bash
git checkout feat/research-engine && git checkout -b feat/research-memory
```

(If the spec commit is already on `feat/research-memory`, skip this step.)

- [ ] **Step 2: Write the failing tests**

`tests/test_memory.py`:

```python
import json, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach, memory  # noqa: E402


def it(n, url=None):
    return {"name": f"Tool{n}", "kind": "tool", "why": "w", "url": url or f"https://www.Example.com/t{n}/"}


class Memory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.saved = coach.STATE; coach.STATE = os.path.join(self.tmp.name, "coach")
        self.file = os.path.join(coach.STATE, "suggestions.json")

    def tearDown(self):
        coach.STATE = self.saved; self.tmp.cleanup()

    def test_item_id_ignores_scheme_case_www_and_trailing_slash(self):
        self.assertEqual(memory.item_id({"url": "https://www.Example.com/T1/"}), "example.com/t1")
        self.assertEqual(memory.item_id({"url": "https://example.com/t1"}), "example.com/t1")
        self.assertEqual(memory.item_id({"name": "  WCAG ", "url": ""}), "wcag")

    def test_an_item_is_shown_with_at_most_two_prompts(self):
        items = [it(1), it(2)]
        self.assertEqual(len(memory.pick(items, key="k1")), 2)
        self.assertEqual(len(memory.pick(items, key="k2")), 2)
        self.assertEqual(memory.pick(items, key="k3"), [])
        self.assertEqual(len(memory.pick(items, key="k1")), 2)                 # the same prompt again does not count twice
        self.assertEqual([i["name"] for i in memory.pick([it(3)], key="k3")], ["Tool3"])

    def test_picking_without_a_key_records_nothing(self):
        for _ in range(3): memory.pick([it(1)])
        self.assertEqual(len(memory.pick([it(1)], key="k1")), 1)

    def test_dismissed_and_adopted_items_are_never_suggested_again(self):
        self.assertTrue(memory.mark(memory.item_id(it(1)), "dismissed"))
        self.assertTrue(memory.mark(memory.item_id(it(2)), "adopted"))
        self.assertEqual([i["name"] for i in memory.pick([it(1), it(2), it(3)], key="k1")], ["Tool3"])
        self.assertEqual(memory.statuses(), {"example.com/t1": "dismissed", "example.com/t2": "adopted"})
        self.assertFalse(memory.mark("example.com/t1", "maybe")); self.assertFalse(memory.mark("", "dismissed"))

    def test_the_limit_caps_what_is_picked(self):
        self.assertEqual(len(memory.pick([it(n) for n in range(8)], key="k1")), 4)

    def test_a_broken_or_huge_file_never_breaks_picking(self):
        os.makedirs(coach.STATE, exist_ok=True)
        with open(self.file, "w") as f: f.write("{broken")
        self.assertEqual(len(memory.pick([it(1)], key="k1")), 1)
        with open(self.file, "w") as f: json.dump({"items": {"x": "not a dict", "example.com/t1": ["nor this"]}}, f)
        self.assertEqual(len(memory.pick([it(1)], key="k2")), 1)
        self.assertEqual(memory.statuses(), {})
        memory.mark("keep.me/x", "dismissed")
        memory.pick([it(n) for n in range(600)], key="k9", limit=600)
        with open(self.file) as f: stored = json.load(f)["items"]
        self.assertLessEqual(len(stored), memory.MAX_KEEP); self.assertEqual(stored["keep.me/x"]["status"], "dismissed")   # choices are kept


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run them to make sure they fail**

Run: `python3 -W error::ResourceWarning -m unittest discover -s tests -p "test_memory.py"`
Expected: ERROR `No module named 'memory'`

- [ ] **Step 4: Write `scripts/memory.py`**

```python
"""memory.py - what the research pass has already shown you, and what you did with it. Local only; never sent anywhere.

<state>/suggestions.json: {"items": {id: {"name", "kind", "url", "shown": [prompt keys], "status": "dismissed"|"adopted", "ts"}}}
An item is shown with at most MAX_SHOWN prompts; one you hid (x) or already use (a) is never suggested again.
"""
import time, urllib.parse

import discover

NAME, MAX_SHOWN, MAX_KEEP = "suggestions.json", 2, 500
STATUSES = ("dismissed", "adopted")


def item_id(item):
    """The same page is the same suggestion, however the model spelled its url."""
    u = urllib.parse.urlsplit(str(item.get("url", "")).strip().lower())
    host = u.hostname or ""
    if host.startswith("www."): host = host[4:]
    return (host + u.path.rstrip("/")) or str(item.get("name", "")).strip().lower()


def _items():
    d = discover._load(NAME).get("items")
    return {k: v for k, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}


def _save(its):
    if len(its) > MAX_KEEP:                       # forget the oldest unmarked ones; your choices are kept
        loose = sorted((k for k, v in its.items() if v.get("status") not in STATUSES), key=lambda k: its[k].get("ts", 0))
        for k in loose[:len(its) - MAX_KEEP]: its.pop(k)
    discover._dump(NAME, {"items": its})


def statuses():
    return {k: v["status"] for k, v in _items().items() if v.get("status") in STATUSES}


def pick(items, key=None, limit=discover.MAX_ITEMS):
    """Up to `limit` items worth showing: none you hid or use, none already shown with MAX_SHOWN other prompts.
    With `key` (the prompt they are shown with) the showing is recorded."""
    its, out = _items(), []
    for x in items:
        rec = its.get(item_id(x), {})
        if rec.get("status") in STATUSES: continue
        if len([k for k in rec.get("shown", []) if k != key]) >= MAX_SHOWN: continue
        out.append(x)
        if len(out) == limit: break
    if key and out:
        for x in out:
            rec = its.setdefault(item_id(x), {})
            rec.update(name=x.get("name", ""), kind=x.get("kind", "tool"), url=x.get("url", ""), ts=time.time())
            if key not in rec.setdefault("shown", []): rec["shown"].append(key)
        try: _save(its)
        except OSError: pass
    return out


def mark(iid, status):
    """Hide an item for good (dismissed) or note that you use it (adopted). False when nothing was saved."""
    if status not in STATUSES or not iid: return False
    its = _items(); its.setdefault(iid, {}).update(status=status, ts=time.time())
    try:
        _save(its); return True
    except OSError:
        return False
```

- [ ] **Step 5: Run the tests**

Run: `python3 -W error::ResourceWarning -m unittest discover -s tests -p "test_memory.py" -v`
Expected: 6 PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/memory.py tests/test_memory.py
git commit -m "feat: memory.py remembers what research showed, and what you hid or use"
```

---

### Task 2: Research picks through memory; research one prompt on demand

**Files:**
- Modify: `scripts/discover.py` (`verify_all` limit, `for_advice` keeps up to 8, `_research` picks, `request(…, fresh=False)`, `main` adds `--key`, new `_advice_for`)
- Modify: `scripts/coach.py` (new `spawn_research`)
- Test: `tests/test_discover.py`

**Interfaces:**
- Consumes: `memory.pick`, `memory.item_id`, `memory.mark` (Task 1).
- Produces: `discover.verify_all(raw, have, get=http_get, stack=(), limit=MAX_ITEMS)`; `discover.for_advice` returns up to `MAX_RAW` verified items; `discover.request(key, session, advice, stack, save, fresh=False)`; CLI `discover.py --key KEY`; `coach.spawn_research(key)`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_discover.py`, add `import memory` next to `import coach, discover`. Add to class `Verify`:

```python
    def test_verify_all_can_keep_more_than_it_shows(self):
        table = {f"https://example.com/{i}": (200, f"tool{i}") for i in range(10)}
        raw = [{"name": f"tool{i}", "url": f"https://example.com/{i}"} for i in range(10)]
        self.assertEqual(len(discover.verify_all(raw, HAVE, getter(table), limit=discover.MAX_RAW)[0]), 8)
```

Add to class `Queue`:

```python
    def test_research_shows_an_item_with_two_prompts_at_most_and_never_a_hidden_one(self):
        for k in ("k1", "k2", "k3"): discover.request(k, "s1", self.adv, [], self.save)
        self.assertEqual(self.got, [("k1", ["GreatKit"]), ("k2", ["GreatKit"])])        # the third prompt gets nothing new
        memory.mark("tools.example.com/g", "dismissed"); self.got.clear()
        discover.request("k4", "s2", {**self.adv, "topic": "other"}, [], self.save)
        self.assertEqual(self.got, [])

    def test_a_forced_request_ignores_the_cache_and_the_pause(self):
        discover.request("k1", "s1", self.adv, [], self.save)
        discover._dump("research-state.json", {"paused_until": time.time() + 3600})
        discover.request("k2", "s1", self.adv, [], self.save, fresh=True)
        self.assertEqual(self.calls(), 2)                                         # a new web call, cache and pause notwithstanding
        self.assertEqual([k for k, _ in self.got], ["k1", "k2"])

    def test_spawn_research_starts_discover_for_one_prompt(self):
        with mock.patch.object(coach, "_spawn") as sp: coach.spawn_research("123.0:abc")
        argv = sp.call_args[0][0]
        self.assertTrue(argv[1].endswith("discover.py")); self.assertEqual(argv[2:], ["--key", "123.0:abc"])
```

Add to class `EndToEnd`:

```python
    def test_research_by_key_runs_fresh_and_the_panel_shows_it(self):
        with tempfile.TemporaryDirectory() as cfg:
            write_history(cfg, [self.TEXT])
            empty = json.dumps({"items": []})
            self.assertEqual(self.job(cfg, FAKE_JSON=self.ADVICE, FAKE_JSON_WEB=empty).returncode, 0)        # analysed, nothing found
            stub = os.path.join(cfg, "stub.json")
            with open(stub, "w") as f: json.dump({"https://tools.example.com/g": {"status": 200, "text": "GreatKit"}}, f)
            key = coach.prompt_key((1750000000.0, "proj", self.TEXT))
            r = run(cfg, "discover.py", "--key", key, FAKE_JSON_WEB=self.WEB, COACHLINE_FETCH_STUB=stub)
            self.assertEqual(r.returncode, 0, r.stderr)
            last = json.loads(read(os.path.join(cfg, "coach", "rewrites.jsonl")).splitlines()[-1])
            self.assertEqual((last["key"], [d["name"] for d in last["discovery"]]), (key, ["GreatKit"]))
            self.assertEqual(read(os.path.join(cfg, "sent.log")).count("WebSearch,WebFetch --setting-sources"), 2)

    def test_research_by_key_refuses_opted_out_and_unanalysed_prompts(self):
        with tempfile.TemporaryDirectory() as cfg:
            write_history(cfg, [self.TEXT])
            key = coach.prompt_key((1750000000.0, "proj", self.TEXT))
            r = run(cfg, "discover.py", "--key", key, FAKE_JSON_WEB=self.WEB)
            self.assertNotEqual(r.returncode, 0); self.assertIn("not analysed yet", r.stderr)
            self.assertNotEqual(run(cfg, "discover.py", "--key", "1.0:nothere").returncode, 0)
            os.makedirs(os.path.join(cfg, "coach"), exist_ok=True)
            with open(os.path.join(cfg, "coach", "llm-off.txt"), "w") as f: f.write("proj\n")
            r = run(cfg, "discover.py", "--key", key, FAKE_JSON_WEB=self.WEB)
            self.assertNotEqual(r.returncode, 0); self.assertIn("llm-off", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(cfg, "sent.log")))
```

`tests/test_cli_safety.py` checks `discover.py` with no args exits 2 and with `--help` exits 0. Keep both true.

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m unittest discover -s tests -p "test_discover.py"`
Expected: errors (`limit` unexpected keyword, `fresh` unexpected keyword, `spawn_research` missing, `--key` unrecognised).

- [ ] **Step 3: Implement in `scripts/discover.py`**

`verify_all`:

```python
def verify_all(raw, have, get=http_get, stack=(), limit=MAX_ITEMS):
    ok, dropped = [], []
    for it in (raw if isinstance(raw, list) else [])[:MAX_RAW]:
        v, why = verify_item(it, have, get, stack=stack)
        if v and v["url"] not in [o["url"] for o in ok]: ok.append(v)
        elif why: dropped.append(why)
    return ok[:limit], dropped
```

In `for_advice`, keep every verified item (memory picks what to show). Change the `verify_all` call to:

```python
        items, _dropped = verify_all(raw, have_names() | {u["name"].lower() for u in advice.get("use", [])}, get, stack, limit=MAX_RAW)
```

and update its docstring's first line to `"""Up to MAX_RAW verified items for this task on this stack (memory.pick chooses what to show). Cached per topic and stack for 7 days. Never raises: research is a bonus.`

`_research`:

```python
def _research(w, save):
    import memory
    items = memory.pick(for_advice(w["advice"], w.get("stack") or (), fresh=bool(w.get("fresh"))), key=w["key"])
    if items: save(w["key"], w["advice"], items)
    # a usage limit: the session is not researched, and its next prompt tries again
    _mark(w.get("session", ""), done=not paused_until())
```

`request` and `_request` gain `fresh=False` and pass it into the want:

```python
def request(key, session, advice, stack, save, fresh=False):
    """...(docstring unchanged)... fresh (asked for by hand) ignores the cache and a usage-limit pause."""
    try: _request(key, session, advice, stack, save, fresh)
    except (OSError, ValueError, KeyError, TypeError, AttributeError): pass


def _request(key, session, advice, stack, save, fresh=False):
    _mark(session, pending=True)                   # its follow-ups wait for this research instead of asking again
    _dump("research-want.json", {"key": key, "session": session, "advice": advice, "stack": list(stack), "fresh": bool(fresh), "ts": time.time()})
```

(Leave the rest of `_request` as it is.)

`main`: factor out the advice lookup, add `--key`, and pick what `--last` shows:

```python
def _advice_for(key):
    """The newest advice recorded for this prompt, or None."""
    adv = None
    try:
        with open(coach.REWRITES, encoding="utf-8") as f:
            for l in f:
                try: d = json.loads(l)
                except ValueError: continue
                if d.get("key") == key and d.get("advice"): adv = d["advice"]
    except OSError:
        pass
    return adv


def main(argv):
    ap = argparse.ArgumentParser(prog="discover.py", description="Search the web for better tools, approaches, docs and reference sites "
                                 "for a prompt's task. Sends a generic topic and your stack to a web search through your Claude subscription.")
    ap.add_argument("--last", action="store_true", help="do it now for your last prompt and print the result")
    ap.add_argument("--key", help="do it now, in the background, for one analysed prompt (the panel's r key)")
    a = ap.parse_args(argv)
    if not (a.last or a.key):
        ap.print_help(); return 2
    import advisor, memory, stackinfo
    if a.key:
        rows = coach.load_full(coach.HIST)
        row = next((r for r in rows if coach.prompt_key(r) == a.key), None)
        if row is None: sys.exit("no prompt with that key")
        if coach.llm_off(row[1]): sys.exit("this project is in llm-off.txt: not sending it anywhere")
        adv = _advice_for(a.key)
        if not adv: sys.exit("not analysed yet: analyse the prompt first")
        request(a.key, row[3], adv, stackinfo.detect(row[1]), coach._save_discovery, fresh=True)
        return 0
    rows = coach.load(coach.HIST); i, fails = coach.last_eval(rows)
    if i is None: sys.exit("no prompt to look at; run `coach.py --doctor`")
    if coach.llm_off(rows[i][1]): sys.exit("this project is in llm-off.txt: not sending it anywhere")
    adv = _advice_for(coach.prompt_key(rows[i]))
    try: adv = adv or advisor.advise(coach.redact(rows[i][2]), fails)
    except (RuntimeError, ValueError) as e: sys.exit(f"advice failed: {e}")
    print(f"kind of task: {adv['task']} - {adv.get('topic') or adv['summary']}\nsearching the web (up to ~4 min)...")
    items = memory.pick(for_advice(adv, stackinfo.detect(rows[i][1]), fresh=True))
    if not items: print("nothing verifiable found (suggestions that fail the checks are dropped)."); return 0
    for _k, t in lines(items, 100): print(t)
    return 0
```

`coach.load_full` rows are `(ts, project, text, session)`, and `coach.prompt_key` reads only `row[0]` and `row[2]`, so it works on them.

- [ ] **Step 4: Implement `coach.spawn_research`** (after `spawn_review`)

```python
def spawn_research(key):
    """Search the web again for one analysed prompt (the panel's r key), in a detached process. Ignores the cache and a usage-limit pause."""
    _spawn([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "discover.py"), "--key", key])
```

- [ ] **Step 5: Run the whole suite**

Run: `python3 -W error::ResourceWarning -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add scripts/discover.py scripts/coach.py tests/test_discover.py
git commit -m "feat: research shows each suggestion with two prompts at most, never a hidden one; discover.py --key researches one prompt again"
```

---

### Task 3: Card: numbered items, References in the enhanced prompt, redraw when research lands

**Files:**
- Modify: `scripts/discover.py` (`item_lines`, `lines(…, numbered=False)`, `references`, `VERB`)
- Modify: `scripts/watch.py` (`import memory`; `build`; `signature`; `card_lines(…, acts=False)`)
- Test: `tests/test_watch.py`

**Interfaces:**
- Consumes: `memory.statuses`, `memory.item_id` (Task 1).
- Produces: `discover.references(items) -> str`; `discover.item_lines(item, n=None, width=96) -> [(kind, text)]`; `discover.lines(items, width=96, numbered=False)`; entries from `watch.build` gain `"items"` (list of item dicts with `"status"`) and `"refs"` (bool), and `"after"` includes the References block; `watch.card_lines(st, ui, i, e, iw, acts=False)`. With `acts=True`, each item is followed by the line `("web", "itemacts", "", "", "item:<id>")`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_watch.py` (add `import memory` after `import coach` in its imports):

```python
WCAG = {"name": "WCAG 2.2", "kind": "docs", "why": "accessibility rules to follow", "url": "https://www.w3.org/TR/WCAG22/", "install": "", "stars": None, "pushed": None}
KIT = {"name": "GreatKit", "kind": "tool", "why": "better", "url": "https://x.example.com/g", "install": "npm i g", "stars": None, "pushed": None}


class Research(Base):
    def setUp(self):
        super().setUp(); history(self.cfg, [("now", "p", SOLID)])

    def entry(self):
        return watch.build(self.path)["entries"][0]

    def test_research_adds_references_to_the_enhanced_prompt_you_copy(self):
        self.analyse(0, SOLID, discovery=[WCAG, KIT])
        e = self.entry()
        self.assertTrue(e["after"].endswith("References (checked links from web research):\n"
                                            "- Follow WCAG 2.2: https://www.w3.org/TR/WCAG22/\n- Use GreatKit: https://x.example.com/g"))
        card = card_of(once(self.cfg, 100, 60))
        for want in ("1. better: WCAG 2.2 (docs)", "2. better: GreatKit (tool)", "Includes references from web research: x hides one"):
            self.assertIn(want, card)

    def test_a_hidden_suggestion_leaves_the_card_and_the_references_and_a_used_one_is_marked(self):
        self.analyse(0, SOLID, discovery=[WCAG, KIT])
        memory.mark(memory.item_id(KIT), "dismissed"); memory.mark(memory.item_id(WCAG), "adopted")
        e = self.entry()
        self.assertEqual([x["name"] for x in e["items"]], ["WCAG 2.2"]); self.assertNotIn("GreatKit", e["after"])
        self.assertIn("1. better: WCAG 2.2 (docs) · you use this", " ".join(t for _k, t in e["disc"]))

    def test_no_references_without_an_enhanced_prompt_or_without_research(self):
        self.analyse(0, SOLID)
        self.assertNotIn("References", self.entry()["after"]); self.assertFalse(self.entry()["refs"])

    def test_p1_records_still_show_with_references(self):
        self.analyse(0, SOLID, discovery=[{"name": "OldKit", "kind": "mcp", "why": "old", "url": "https://old.example.com/k", "install": "", "stars": 5, "pushed": None}])
        e = self.entry()
        self.assertIn("- Use OldKit: https://old.example.com/k", e["after"])
        self.assertIn("1. better: OldKit (mcp)", " ".join(t for _k, t in e["disc"]))

    def test_research_landing_redraws_the_standalone_panel(self):
        self.analyse(0, SOLID)
        before = watch.signature(watch.build(self.path))
        self.analyse(0, SOLID, discovery=[KIT])
        self.assertNotEqual(before, watch.signature(watch.build(self.path)))

    def test_the_pane_gets_hide_and_use_actions_per_item(self):
        self.analyse(0, SOLID, discovery=[WCAG, KIT])
        st = watch.build(self.path); e = st["entries"][0]
        acts = [l[4] for l in watch.card_lines(st, watch.new_ui(), 0, e, 80, acts=True) if l[1] == "itemacts"]
        self.assertEqual(acts, ["item:w3.org/tr/wcag22", "item:x.example.com/g"])
        self.assertFalse([l for l in watch.card_lines(st, watch.new_ui(), 0, e, 80) if l[1] == "itemacts"])   # never in the terminal panel
```

The P1 item keeps its stored kind `mcp` in the label because it was stored before P1 mapped old kinds to `tool`. `references` treats any kind it doesn't know as `Use`.

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m unittest discover -s tests -p "test_watch.py"`
Expected: failures and errors (`KeyError: 'items'`, missing References, `card_lines` has no `acts`).

- [ ] **Step 3: Implement in `scripts/discover.py`** (replace `lines`)

```python
VERB = {"tool": "Use", "tech": "Consider", "docs": "Follow", "inspo": "Take visual cues from"}


def references(items):
    """The block added to the enhanced prompt, so Claude Code gets the checked links with the task."""
    if not items: return ""
    return "References (checked links from web research):\n" + "\n".join(f"- {VERB.get(it.get('kind'), 'Use')} {it['name']}: {it['url']}" for it in items)


def item_lines(it, n=None, width=96):
    """One item: the 'better:' line (numbered on the panel), then where it comes from and how to install it."""
    import textwrap
    head = (f"{n}. " if n else "") + f"better: {it['name']} ({it['kind']})" + (" · you use this" if it.get("status") == "adopted" else "") + f" - {it['why']}"
    out = [("better", w) for w in textwrap.wrap(head, width, subsequent_indent="        ")]
    meta = " · ".join(x for x in (f"{_stars(it['stars'])} stars" if it.get("stars") is not None else "", f"pushed {it['pushed']}" if it.get("pushed") else "") if x)
    out.append(("src", "  " + (meta + " · " if meta else "") + it["url"]))
    if it.get("install"): out.append(("src", "  install: " + it["install"]))
    return out


def lines(items, width=96, numbered=False):
    """[(kind, text)] for the panel. Says plainly that these are web-found and unverified beyond the checks."""
    if not items: return []
    out = [("dim", "web-found, not installed; only the checks above were verified. read before installing:")]
    for n, it in enumerate(items, 1): out += item_lines(it, n if numbered else None, width)
    return out
```

- [ ] **Step 4: Implement in `scripts/watch.py`**

Add `import memory` after `import discover`. In `build`, read the statuses once before the loop:

```python
    mem = memory.statuses()
```

and replace the `after = …` line and the entry's `"after"` / `"disc"` fields:

```python
        after = adv.get("after") or (re.sub(r"^AFTER:\s*", "", rec.get("text", "")).strip() if rec.get("text") else "")
        items = [dict(x, status=mem.get(memory.item_id(x))) for x in rec.get("discovery") or []
                 if isinstance(x, dict) and x.get("url") and mem.get(memory.item_id(x)) != "dismissed"]
        refs = discover.references(items) if after else ""
```

```python
        st["entries"].append({"ts": ts, "key": key, "text": tidy(coach.redact(text))[:2000], "fails": fails,
                              "fixes": [f"{n}: {coach.FIX[n]}" for n in fails], "advice": adv, "after": after + ("\n\n" + refs if refs else ""),
                              "refs": bool(refs), "items": items, "disc": discover.lines(items, 200, numbered=True),
                              "error": None if adv else rec.get("error"), "off": coach.llm_off(proj), "advisable": coach.advisable(text, fails)})
```

`signature`: count research items and the pause:

```python
def signature(st):
    return (st.get("session"), len(st["entries"]), sum(bool(e["advice"]) + bool(e["error"]) for e in st["entries"]), len(st["insights"]),
            st["learned"].get("generated"), st["review_running"], st["ai"], sum(len(e.get("items", [])) for e in st["entries"]),
            st.get("research_paused"))
```

`card_lines`: the signature gains `acts=False`. Inside, after the enhanced prompt lines, add the note. Then build "Worth a look" from the items, so the pane can get per-item actions:

```python
def card_lines(st, ui, i, e, iw, acts=False):
```

Replace the existing `if e["after"]:` block and the `found = …` / `if found:` block with:

```python
        if e["after"]:
            copied = time.time() - ui["copied"].get(e["key"], 0) < 8
            out += [("", "blank", "", "", None), ("enh", "head", "Enhanced prompt", "✓ Copied" if copied else "c Copy", "copy")]
            for ln in e["after"].splitlines(): out += [("enh", "enh", w, "", None) for w in wrap(ln, iw)]
            if e.get("refs"):
                out += [("enh", "bluedim", w, "", None) for w in wrap("Includes references from web research: x hides one, a marks one you use, r looks again.", iw)]
        if e.get("items"):
            out += [("", "blank", "", "", None), ("web", "head", "Worth a look", "found on the web, not installed", None)]
            for n, it in enumerate(e["items"], 1):
                for k, x in discover.item_lines(it, n, 200): out += [("web", k, w, "", None) for w in wrap(x, iw, "  ")]
                if acts: out.append(("web", "itemacts", "", "", "item:" + memory.item_id(it)))
        elif st.get("research_paused"):
            out.append(("", "blank", "", "", None))
            out += [("info", "bluedim", w, "", None) for w in wrap(f"web research paused until {st['research_paused']} (usage limit); the enhanced prompt still works", iw)]
```

`wrap("", iw)` returns `[""]`, so the blank line between the prompt and the References block stays, and the card reads exactly what Copy copies.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -W error::ResourceWarning -m unittest discover -s tests`
Expected: OK. If an older test asserts the exact `after` text of a prompt that has a `discovery` record, it now ends with the References block. Update that assertion to the new text, because the new text is the spec.

- [ ] **Step 6: Commit**

```bash
git add scripts/discover.py scripts/watch.py tests/test_watch.py
git commit -m "feat: numbered web suggestions, a References block in the enhanced prompt, hidden ones gone at once, redraw when research lands"
```

---

### Task 4: Terminal panel keys `x`, `a`, `r`

**Files:**
- Modify: `scripts/watch.py` (`ALIASES`, `IO`, `handle`, new `_mark`, `loop`)
- Test: `tests/test_watch.py`

**Interfaces:**
- Consumes: `memory.mark`, `memory.item_id` (Task 1); `coach.spawn_research` (Task 2); entry `"items"` (Task 3).
- Produces: `watch.IO.mark(iid, status) -> bool`, `watch.IO.research(key)`; `ui["pick"]` (pending `"dismiss"`/`"adopt"`), `ui["reload"]` (the loop rebuilds state).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_watch.py`:

```python
class WebIO:
    def __init__(self): self.marks, self.researched, self.copied = [], [], []
    def mark(self, iid, status): self.marks.append((iid, status)); return memory.mark(iid, status)
    def research(self, key): self.researched.append(key)
    def copy(self, text): self.copied.append(text); return "fake"


class WebKeys(Base):
    def setUp(self):
        super().setUp(); history(self.cfg, [("now", "p", SOLID)]); self.io = WebIO()

    def test_x_then_a_number_hides_that_suggestion_and_the_copy_follows(self):
        self.analyse(0, SOLID, discovery=[WCAG, KIT])
        frames = self.drive(["x", "2", "c"], W=100, H=60, io=self.io)
        self.assertEqual(self.io.marks, [("x.example.com/g", "dismissed")])
        self.assertIn("press 1-2", frames[1])
        self.assertIn("hidden: GreatKit will not be suggested again", flat(frames[2])); self.assertNotIn("better: GreatKit", frames[2])
        self.assertNotIn("GreatKit", self.io.copied[0]); self.assertIn("WCAG 2.2", self.io.copied[0])

    def test_with_one_suggestion_a_marks_it_at_once(self):
        self.analyse(0, SOLID, discovery=[KIT])
        frames = self.drive(["a"], io=self.io)
        self.assertEqual(self.io.marks, [("x.example.com/g", "adopted")]); self.assertIn("noted: you use GreatKit", flat(frames[-1]))

    def test_any_other_key_cancels_the_choice(self):
        self.analyse(0, SOLID, discovery=[WCAG, KIT])
        self.drive(["x", "esc", "2", "a", "j", "1"], io=self.io)
        self.assertEqual(self.io.marks, [])

    def test_x_without_suggestions_says_so(self):
        self.analyse(0, SOLID)
        self.assertIn("no web suggestions on this prompt", flat(self.drive(["x"], io=self.io)[-1]))

    def test_r_researches_the_selected_prompt_again_once_it_is_analysed(self):
        self.assertIn("analyse this prompt first", flat(self.drive(["r"], io=self.io)[-1]))
        self.analyse(0, SOLID)
        frames = self.drive(["r"], io=self.io)
        self.assertEqual(self.io.researched, [key_for(0, SOLID)]); self.assertIn("searching the web", flat(frames[-1]))
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m unittest discover -s tests -p "test_watch.py"`
Expected: failures (no marks recorded, messages missing).

- [ ] **Step 3: Implement in `scripts/watch.py`**

`ALIASES`: add `"x": "dismiss", "a": "adopt", "r": "research"` to the dict.

`IO`: add the two operations:

```python
IO = type("IO", (), {"copy": staticmethod(coach.copy_text), "enhance": staticmethod(coach.spawn_key),
                     "review": staticmethod(coach.spawn_review), "install": staticmethod(review.install_skill),
                     "mark": staticmethod(memory.mark), "research": staticmethod(coach.spawn_research)})  # swapped for fakes in tests
```

Add before `handle`:

```python
def _mark(ui, it, action, io):
    status = "dismissed" if action == "dismiss" else "adopted"
    if io.mark(memory.item_id(it), status):
        ui["reload"] = True                                                   # the card and the copy drop it now, not on the next reload
        ui["msg"] = (f"hidden: {it['name']} will not be suggested again" if status == "dismissed"
                     else f"noted: you use {it['name']}; it will not be suggested again")
    else:
        ui["msg"] = "could not save that choice (see /coach doctor)"
    return False
```

In `handle`, directly after `n = len(st["entries"]); i, e = cur_entry(ui, st)`, add:

```python
    pick, ui["pick"] = ui.get("pick"), None
    if pick:                                                                  # x or a asked "which one?": a number answers, anything else cancels
        its = e["items"] if e else []
        if isinstance(key, str) and key.isdigit() and 1 <= int(key) <= len(its): return _mark(ui, its[int(key) - 1], pick, io)
        ui["msg"] = "cancelled"
        return False
    if key in ("dismiss", "adopt"):
        its = e["items"] if e else []
        if not its: ui["msg"] = "no web suggestions on this prompt"
        elif len(its) == 1: return _mark(ui, its[0], key, io)
        else:
            ui["pick"] = key
            ui["msg"] = f"which one? press 1-{len(its)} to {'hide it' if key == 'dismiss' else 'mark it as one you use'} (any other key cancels)"
        return False
    if key == "research":
        if e is None or not e["advice"]: ui["msg"] = "analyse this prompt first (e), then r looks on the web again"
        elif e["off"]: ui["msg"] = "this project is in llm-off.txt: not sending it anywhere"
        else:
            io.research(e["key"])
            ui["msg"] = "searching the web for this task in the background (up to ~4 minutes); the card updates by itself"
        return False
```

Note: a cancelling key is consumed (it does not also run its own action). That is what `test_any_other_key_cancels_the_choice` pins: `a` and `1` after a cancelled `x` must not mark anything. `a` starts a new choice, and `j` cancels it.

`loop`: after `if handle(ui, st, k, io): return`, rebuild state when a key changed what is stored:

```python
        if handle(ui, st, k, io): return
        if ui.pop("reload", False): st = load_state(); last_load = clock()
```

- [ ] **Step 4: Run the whole suite**

Run: `python3 -W error::ResourceWarning -m unittest discover -s tests`
Expected: OK. `test_select.Panel` tests pass `io` fakes without `mark`/`research`; they never press those keys, so nothing changes for them.

- [ ] **Step 5: Commit**

```bash
git add scripts/watch.py tests/test_watch.py
git commit -m "feat: panel keys x hides a web suggestion, a marks one you use, r looks on the web again"
```

---

### Task 5: Claude Code pane: Hide / I use this / Look again

**Files:**
- Modify: `scripts/pane.py` (`--mark`, `--research`; `tick` passes `acts=True`)
- Modify: `hooks/coachline.tsx` (render `itemacts` lines as two buttons; Look again button)
- Test: `tests/test_pane.py`, `hooks/coachline.test.ts`

**Interfaces:**
- Consumes: `watch.card_lines(…, acts=True)` and its `("web", "itemacts", "", "", "item:<id>")` lines (Task 3); `memory.mark` (Task 1); `coach.spawn_research` (Task 2).
- Produces: `pane.py --mark dismissed|adopted ID` (prints a message, exit 0; 2 on a bad status); `pane.py --research KEY [--session S]`. Button keys in the pane: `hide:<id>`, `use:<id>`, `research`.

- [ ] **Step 1: Write the failing Python tests**

Add to `tests/test_pane.py` class `Tick`:

```python
    def write_rec(self, rec):
        with open(coach.REWRITES, "a", encoding="utf-8") as f: f.write(json.dumps(rec) + "\n")

    def test_web_suggestions_come_with_hide_and_use_actions(self):
        history(self.cfg, [("s1", "p", SOLID)])
        from test_watch import key_for, ADVICE
        self.write_rec({"key": key_for(0, SOLID), "text": "AFTER: x", "advice": ADVICE,
                        "discovery": [{"name": "GreatKit", "kind": "tool", "why": "w", "url": "https://x.example.com/g", "install": "", "stars": None, "pushed": None}]})
        st = self.tick()
        self.assertIn(["web", "itemacts", "", "", "item:x.example.com/g"], st["entries"][0]["lines"])
        self.assertIn("References (checked links from web research):", st["entries"][0]["after"])

    def test_mark_and_research_from_the_pane(self):
        import memory
        self.assertEqual(pane.main(["--mark", "dismissed", "x.example.com/g"]), 0)
        self.assertEqual(memory.statuses(), {"x.example.com/g": "dismissed"})
        self.assertEqual(pane.main(["--mark", "maybe", "x.example.com/g"]), 2)
        with mock.patch.object(coach, "spawn_research") as sr:
            self.assertEqual(pane.main(["--research", "123.0:abc", "--session", "s1"]), 0)
        sr.assert_called_once_with("123.0:abc")
```

Run: `python3 -m unittest discover -s tests -p "test_pane.py"`
Expected: failures (no `itemacts` line; `--mark` unrecognised).

- [ ] **Step 2: Implement in `scripts/pane.py`**

Docstring, add two usage lines:

```
  python pane.py --mark dismissed|adopted ID       hide a web suggestion for good, or note that you use it (the pane's buttons)
  python pane.py --research KEY [--session ID]     search the web again for one analysed prompt (the pane's Look again button)
```

`tick`: pass `acts=True` to `watch.card_lines(st, ui, i, e, iw, acts=True)`.

`main`: add the arguments and their handling before `if a.json and a.session:`:

```python
    ap.add_argument("--mark", nargs=2, metavar=("STATUS", "ID")); ap.add_argument("--research", metavar="KEY")
```

```python
    if a.mark:
        import memory
        status, iid = a.mark
        if status not in memory.STATUSES: print("status must be dismissed or adopted", file=sys.stderr); return 2
        if not memory.mark(iid, status): print("could not save that choice", file=sys.stderr); return 1
        print("hidden: it will not be suggested again" if status == "dismissed" else "noted: it will not be suggested again"); return 0
    if a.research:
        coach.spawn_research(a.research)
        print("searching the web for this task in the background (up to ~4 minutes)"); return 0
```

Run: `python3 -W error::ResourceWarning -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 3: Write the failing pane tests**

Add to `hooks/coachline.test.ts`:

```ts
const WITH_WEB = {
  ...ENTRY, glyph: '✓', state: 'done', words: 'analysed', after: 'Do it.\n\nReferences (checked links from web research):\n- Use GreatKit: https://x.example.com/g',
  lines: [['prompt', 'head', 'Your prompt', '15:28 · ✓ analysed', null], ['web', 'better', '1. better: GreatKit (tool) - w', '', null],
          ['web', 'itemacts', '', '', 'item:x.example.com/g']],
}

test('Hide, I use this and Look again call pane.py with the item and the prompt', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  const ran: string[][] = []
  on('process.run', ($, e) => {
    ran.push([...e.argv])
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    return RESULT(e.argv.includes('--mark') || e.argv.includes('--research') ? 'ok' : STATE({ entries: [WITH_WEB] }))
  })
  await $.session.start(START)
  await settle()
  await $.prompt.submit(SUBMIT)
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  await ui.press({ key: 'hide:x.example.com/g' })
  await ui.press({ key: 'use:x.example.com/g' })
  await ui.press({ key: 'research' })
  const tail = (flag: string) => ran.find(a => a.includes(flag))?.slice(-3)
  expect(tail('dismissed')).toEqual(['--mark', 'dismissed', 'x.example.com/g'])
  expect(tail('adopted')).toEqual(['--mark', 'adopted', 'x.example.com/g'])
  expect(ran.find(a => a.includes('--research'))?.slice(-4)).toEqual(['--research', 'k1', '--session', 's1'])
})
```

Run: `claude plugin test .`
Expected: the new test fails (no such buttons).

- [ ] **Step 4: Implement in `hooks/coachline.tsx`**

Next to `analyse` and `install`, add:

```tsx
    const mark = async (status: 'dismissed' | 'adopted', id: string) => {
      const r = await run($, ['--mark', status, id])
      await update($, msg, () => (r.ok ? r.out.trim() : r.err))
      await refresh($)
    }
    const research = async () => {
      const r = await run($, s.session ? ['--research', cur.key, '--session', s.session] : ['--research', cur.key])
      await update($, msg, () => (r.ok ? r.out.trim() : r.err))
    }
```

In `line`, before the `if (action === 'enter')` line:

```tsx
      if (kind === 'itemacts' && action?.startsWith('item:')) {
        const id = action.slice('item:'.length)
        return (
          <Box key={`l${n}`}>
            <Text>{'  '}</Text>
            <Button key={`hide:${id}`} label="Hide" onPress={() => mark('dismissed', id)} />
            <Text>{'  '}</Text>
            <Button key={`use:${id}`} label="I use this" onPress={() => mark('adopted', id)} />
          </Box>
        )
      }
```

After the Analyse button in the returned tree:

```tsx
        {!!cur.after && cur.state !== 'off' && <Button key="research" label="Look again on the web" onPress={research} />}
```

- [ ] **Step 5: Run both suites**

Run: `claude plugin test .`
Expected: 12 pass, 0 fail.
Run: `python3 -W error::ResourceWarning -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add scripts/pane.py hooks/coachline.tsx hooks/coachline.test.ts tests/test_pane.py
git commit -m "feat: the Claude Code pane hides or marks a web suggestion and looks again on the web"
```

---

### Task 6: Docs

**Files:**
- Modify: `README.md`, `skills/coach/SKILL.md`

- [ ] **Step 1: README**

- Keys table, after the `s` row, add:
  `| `x` | Hide a web suggestion for good (asks which one when there are several) |`
  `| `a` | Mark a web suggestion as one you already use, so it is not suggested again |`
  `| `r` | Look on the web again for the selected prompt (ignores the cache and a usage-limit pause) |`
- Features: after the "Research for each new task" bullet, add:
  `- **Remembers what it showed you**: a suggestion appears with two prompts at most, never again once you hide it or say you use it, and its checked links are added to the enhanced prompt as References, so Claude Code gets them with your task.`
- Privacy: add `- What you hid or use is kept in ~/.claude/coach/suggestions.json, on your machine only.`

- [ ] **Step 2: `/coach` skill**

In the `/coach watch` bullet, after "`s` installs a drafted skill", add: "`x` hides a web suggestion, `a` marks one you use, `r` looks on the web again,".

- [ ] **Step 3: Full suites and commit**

Run: `python3 -W error::ResourceWarning -m unittest discover -s tests` → OK; `claude plugin test .` → all pass.

```bash
git add README.md skills/coach/SKILL.md
git commit -m "docs: x, a and r; suggestions are remembered locally and added to the enhanced prompt as References"
```

---

## Self-review notes

- Spec P2 coverage:
  - Memory and the 2-prompt limit (Tasks 1–2)
  - Hidden items vanish at once (Task 3 display filter + Task 4 reload)
  - References block and the "updated" note (Task 3)
  - Keys (Task 4) and pane buttons (Task 5)
  - `r` / Look again (Tasks 2, 4, 5)
  - The redraw fix (Task 3 `signature`)
  - Docs (Task 6)
- P3 (the history review reports adopted / ignored items) stays out of scope.
