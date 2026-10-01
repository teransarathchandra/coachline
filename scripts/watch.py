"""watch.py - the coachline panel: THIS THREAD only, one column, analysed by Claude. No animation.

Top: the prompt you are looking at (the newest by default) in white, then what can be improved in blue, then the
ENHANCED PROMPT as a block you copy with `c`. Below: a one-line summary of patterns Claude found in your past chats
(`i` to read), and a compact list of this thread's prompts with a status glyph each. Up/Down move through the list.

  Up / Down (k / j, p / n)  select an earlier / later prompt          g / G   oldest / newest
  PgUp / PgDn (b / space)   scroll the card when it is taller than the pane
  Enter                     open the selected prompt full width as plain text (Esc closes)
  c                         copy the enhanced prompt to the clipboard, exactly as written
  e                         have Claude analyse the selected prompt now
  i                         read / hide the patterns from your past chats
  s                         install the skill Claude drafted for a request you keep repeating (never overwrites)
  q or Ctrl+C               quit

  python watch.py            interactive
  python watch.py --once     print one plain frame and exit (also used when stdin is not a terminal)

Status glyphs: ✓ analysed   … analysing or queued   ! can be improved (local hints)   × analysis failed   – opted out   · nothing to add

With Claude analysis on (setup.py --panel-ai on) the panel itself starts the background `claude -p` jobs on your subscription:
the newest unanalysed prompts of this thread, and a review of your history every ~2 days. Redacted; llm-off.txt projects never sent.
The screen redraws only on a key or when new data arrives.
"""
import argparse, datetime as dt, json, os, re, shutil, sys, textwrap, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import advisor
import coach
import discover
import review

POSIX_KEYS = {"[A": "up", "[B": "down", "[5~": "pgup", "[6~": "pgdn", "[H": "home", "[F": "end", "[1~": "home", "[4~": "end",
              "OA": "up", "OB": "down", "OH": "home", "OF": "end"}
WIN_KEYS = {"H": "up", "P": "down", "I": "pgup", "Q": "pgdn", "G": "home", "O": "end"}
ALIASES = {"k": "up", "j": "down", "p": "up", "n": "down", "b": "pgup", " ": "pgdn", "g": "home", "G": "end", "\x03": "q", "Q": "q",
           "c": "copy", "e": "enhance", "s": "skill", "i": "patterns", "\r": "enter", "\n": "enter", "\x1b": "esc"}
IO = type("IO", (), {"copy": staticmethod(coach.copy_text), "enhance": staticmethod(coach.spawn_key),
                     "review": staticmethod(coach.spawn_review), "install": staticmethod(review.install_skill)})  # swapped for fakes in tests
# your words white; what can be improved blue (bright blue reads on dark and light terminals); structure in grey
CODE = {"title": "1", "meta": "90", "prompt": "1;97", "label": "1;94", "blue": "94", "bluedim": "2;94", "enh": "94", "rule": "90", "blank": "0",
        "ok": "92", "warn": "93", "bad": "91", "key": "1;97", "task": "2;94", "better": "1;94", "src": "2;94", "dim": "2;94", "use": "94",
        "get": "94", "tip": "94", "flow": "2;94", "head": "1;94", "after": "94", "sel": "7"}
PENDING_SECONDS = 150
MAX_WIDTH = 100                      # lines longer than this are hard to read, however wide the pane is
GLYPHS = {"done": ("✓", "ok"), "pending": ("…", "warn"), "error": ("×", "bad"), "off": ("–", "meta"),
          "local": ("!", "blue"), "quiet": ("·", "meta")}


# ---------------------------------------------------------------- data
load_full = coach.load_full


def rewrites():
    out = {}
    try:
        with open(coach.REWRITES, encoding="utf-8") as f:
            for l in f:
                try: d = json.loads(l); out[d["key"]] = d
                except (ValueError, KeyError, TypeError): continue
    except OSError:
        pass
    return out


def review_running():
    try: return time.time() - os.path.getmtime(coach.REVIEW_LOCK) < 900
    except OSError: return False


def _matches(texts, keywords):
    return sum(1 for t in texts if any(coach.has_kw(t, k) for k in keywords))


def insights(entries, rows, L):
    """What Claude learned from your whole history (learned.json) that is relevant to THIS thread. Counts are recomputed locally."""
    here_txt = [e["text"].lower() for e in entries]
    all_txt = [coach.redact(t).lower() for _ts, _p, t, _s in rows if coach.scorable(t)]
    out = []
    for r in L.get("requests", []):
        here = _matches(here_txt, r.get("keywords", []))
        if not here: continue
        past = max(_matches(all_txt, r.get("keywords", [])) - here, 0)
        slug = r["name"]
        drafted = os.path.isfile(os.path.join(coach.STATE, "drafts", slug, "SKILL.md"))
        installed = os.path.isfile(os.path.join(coach.CONFIG, "skills", slug, "SKILL.md"))
        out.append({"kind": "request", "name": slug, "past": past, "here": here, "drafted": drafted, "installed": installed,
                    "slug": slug if drafted and not installed else None})
    for m in L.get("mistakes", []):
        here = _matches(here_txt, m.get("keywords", []))
        if not here: continue
        out.append({"kind": "mistake", "name": m["name"], "past": max(_matches(all_txt, m.get("keywords", [])) - here, 0), "here": here,
                    "fix": m.get("fix", ""), "slug": None})
    return out


def build(path):
    """State for render(): THIS thread's prompts (the session of the newest history entry) plus what Claude knows from the rest."""
    rows = load_full(path); aft = rewrites(); L = coach.learned()
    st = {"entries": [], "insights": [], "learned": L, "ai": coach.ai_on(), "review_running": review_running(), "total": 0}
    if not rows: return st
    cur = rows[-1][3]; prev = None
    for ts, proj, text, sid in rows:
        gap = None if prev is None else ts - prev; prev = ts
        if sid != cur or not coach.scorable(text) or text.startswith("/coach"): continue
        fails = [n for n, fn in coach.RULES if not fn(text, gap)]
        key = coach.prompt_key((ts, proj, text)); rec = aft.get(key) or {}; adv = rec.get("advice") or {}
        after = adv.get("after") or (re.sub(r"^AFTER:\s*", "", rec.get("text", "")).strip() if rec.get("text") else "")
        st["entries"].append({"ts": ts, "key": key, "text": coach.redact(text).replace("\n", " ")[:2000], "fails": fails,
                              "fixes": [f"{n}: {coach.FIX[n]}" for n in fails], "advice": adv, "after": after,
                              "disc": discover.lines(rec["discovery"], 200) if rec.get("discovery") else [],
                              "error": None if adv else rec.get("error"), "off": coach.llm_off(proj), "advisable": coach.advisable(text, fails)})
    st["insights"] = insights(st["entries"], rows, L)
    return st


def signature(st):
    return (len(st["entries"]), sum(bool(e["advice"]) + bool(e["error"]) for e in st["entries"]), len(st["insights"]),
            st["learned"].get("generated"), st["review_running"], st["ai"])


# ---------------------------------------------------------------- presentation helpers
def clip(s, w):
    return s if len(s) <= w else s[:max(w - 1, 0)] + "…"


def wrap(s, w, indent=""):
    return textwrap.wrap(s, max(w, 8), subsequent_indent=indent) or [""]


def bullet(s, w, maxlines=2):
    """'• text' wrapped with a hanging indent, cut after maxlines with an ellipsis so one long tip cannot crowd out the rest."""
    lines = wrap("• " + s, w, "  ")
    if len(lines) > maxlines: lines = lines[:maxlines]; lines[-1] = clip(lines[-1] + " ", w - 1) + "…"
    return lines


def stamp(ts):
    d = dt.datetime.fromtimestamp(ts)
    return d.strftime("%H:%M") if d.date() == dt.date.today() else d.strftime("%b %d %H:%M")


def status(e, st, ui):
    """(state, glyph, colour kind, words) for one prompt."""
    if e["advice"]: return ("done",) + GLYPHS["done"] + ("analysed",)
    if e["error"]: return ("error",) + GLYPHS["error"] + ("analysis failed",)
    if e["off"]: return ("off",) + GLYPHS["off"] + ("opted out of Claude",)
    if time.time() - ui["pending"].get(e["key"], 0) < PENDING_SECONDS: return ("pending",) + GLYPHS["pending"] + ("analysing",)
    if e["key"] in ui["tried"]: return ("error",) + GLYPHS["error"] + ("no answer yet, press e to retry",)    # started, never finished
    if st["ai"] and e["advisable"] and any(x is e for x in st["entries"][-5:]): return ("pending",) + GLYPHS["pending"] + ("queued for analysis",)
    if e["fails"]: return ("local",) + GLYPHS["local"] + ("can be improved",)
    return ("quiet",) + GLYPHS["quiet"] + ("nothing to add",)


def pattern_texts(st):
    """Plain-English one-liners about patterns from your past chats that also appear in this thread."""
    out = []
    for x in st["insights"]:
        total = x["past"] + x["here"]
        if x["kind"] == "request":
            head = f'You have asked for "{x["name"]}" {total} times' + (f" ({x['past']} before this thread)" if x["past"] else "")
            tail = (f"you already have /{x['name']}, use it" if x["installed"] else
                    f"press s to install the drafted skill /{x['name']}" if x["drafted"] else "/coach review can draft a skill for it")
            out.append(f"{head}: {tail}")
        else:
            fix = re.split(r"(?<=[.!?])\s", x.get("fix", "").strip(), maxsplit=1)[0][:110]
            out.append(f"Habit: {x['name'].replace('-', ' ')}, seen {total} times. {fix}".rstrip())
    return out


def cur_entry(ui, st):
    """(index, entry) of the selected prompt: the newest unless Up / Down chose an earlier one. (None, None) when there are none."""
    es = st["entries"]
    if not es: return None, None
    i = len(es) - 1 if ui["sel"] is None else min(max(ui["sel"], 0), len(es) - 1)
    return i, es[i]


def card_lines(st, ui, i, e, iw, level=0):
    """[(kind, text)]: the prompt you are looking at, what to improve, the enhanced prompt.
    level 0 = everything, 1 = fewer tips, 2 = one tip and no extras: used to keep the enhanced prompt on screen in a short pane."""
    out = []
    _s, glyph, kind, words = status(e, st, ui)
    older = ui["sel"] is not None and i != len(st["entries"]) - 1
    out.append(("meta", f"{stamp(e['ts'])}  ·  {words}" + ("   (an earlier prompt: G = newest)" if older else "")))
    pl = wrap(e["text"], iw)
    cut = len(pl) > 5
    if cut: pl = pl[:5]; pl[-1] = clip(pl[-1] + " ", iw - 1) + "…"
    out += [("prompt", w) for w in pl] + ([("meta", "Enter shows the whole prompt")] if cut else []) + [("blank", "")]
    adv = e["advice"]
    if adv:
        if adv.get("summary") and level == 0: out.append(("task", clip(f"{adv.get('task', 'other')} · {adv['summary']}", iw)))
        bullets = list(adv.get("tips", [])[:(3, 2, 1)[level]])
        bullets += [f"use /{u['name']}" + (f": {u['why']}" if u.get("why") else "") for u in adv.get("use", [])[:(2, 2, 0)[level]]]
        bullets += [f"get {g['name']}" + (f": {g['why']}" if g.get("why") else "") for g in adv.get("get", [])[:(1, 0, 0)[level]]]
        if bullets:
            out.append(("label", "Improve"))
            for b in bullets: out += [("blue", w) for w in bullet(b, iw)]
            out.append(("blank", ""))
        if e["after"]:
            copied = time.time() - ui["copied"].get(e["key"], 0) < 8
            out.append(("label", "Enhanced prompt  ✓ copied" if copied else "Enhanced prompt  ·  c to copy"))
            for ln in e["after"].splitlines(): out += [("enh", w) for w in wrap(ln, iw)]
        found = [(k, x) for k, x in e["disc"] if k != "dim"]
        if found:
            out += [("blank", ""), ("label", "Worth a look  (found on the web, not installed)")]
            for k, x in found: out += [(k, w) for w in wrap(x, iw, "  ")]
        return out
    if e["error"]:
        out.append(("bluedim", f"Claude's analysis failed ({str(e['error'])[:80]}). Press e to try again."))
        return out
    if e["off"]:
        out.append(("bluedim", "This project is in llm-off.txt, so it is never sent to Claude."))
        return out
    if kind == "warn":
        out.append(("bluedim", "Claude is analysing this prompt, usually about 20 seconds. This updates by itself."))
    hints = [f.split(": ", 1)[1] for f in e["fixes"]]
    if hints:
        out.append(("label", "While you wait" if kind == "warn" else "Improve"))
        for h in hints: out += [("blue", w) for w in bullet(h, iw)]
    elif kind != "warn":
        out.append(("bluedim", "Nothing to improve here."))
    if not st["ai"]:
        out.append(("blank", ""))
        out.append(("bluedim", "Press e for Claude's analysis and an enhanced prompt."))
        out += [("bluedim", w) for w in wrap("Analyse every prompt automatically: " + coach.py_cmd("setup.py", "--panel-ai", "on"), iw, "  ")]
    return out


# ---------------------------------------------------------------- rendering
def new_ui():
    return {"sel": None, "lo": 0, "cs": 0, "detail": False, "dscroll": 0, "pending": {}, "tried": set(), "review_after": 0.0, "msg": "",
            "patterns": False, "copied": {}}


def footer_text(W, detail):
    items = ([("Esc", "back"), ("c", "copy"), ("e", "analyse"), ("↑↓", "scroll"), ("q", "quit")] if detail else
             [("↑↓", "prompt"), ("c", "copy"), ("e", "analyse"), ("Enter", "full"), ("i", "patterns"), ("s", "skill"), ("q", "quit")])
    out, used = [], 1
    for key, label in items:
        need = len(key) + 1 + len(label) + (2 if out else 0)
        if used + need > W - 1: break
        out.append((key, label)); used += need
    return out


def render(st, ui, W, H, color=True):
    """The frame as a list of lines. Pure apart from scroll bookkeeping written into ui."""
    def c(kind, s): return f"\033[{CODE[kind]}m{s}\033[0m" if color and CODE[kind] != "0" else s
    W = max(W, 30); H = max(H, 10)
    i, e = cur_entry(ui, st)
    if ui["detail"] and e is not None: return detail_frame(st, ui, i, e, W, H, color)
    iw = min(W - 3, MAX_WIDTH)
    es = st["entries"]; n = len(es); narrow = W < 64
    # header: where you are, and whether Claude is on
    working = st["review_running"] or any(status(x, st, ui)[0] == "pending" for x in es)
    word, kind, dot = (("Claude off", "meta", "○") if not st["ai"] else ("Claude working…", "warn", "●") if working else ("Claude on", "ok", "●"))
    left = f" coachline · this thread · {n} prompt{'s' if n != 1 else ''}"
    right = f"{dot} {word} "
    if len(left) + len(right) + 2 > W - 1: left = " coachline"
    if len(left) + len(right) + 1 > W - 1: right = f"{dot} "
    head = c("title", left) + " " * max(W - 1 - len(left) - len(right), 1) + c(kind, right)
    rule = c("rule", " " + "─" * (W - 3))
    # patterns: one line, or the list when expanded
    pats = pattern_texts(st); pat_rows = []
    if pats and ui["patterns"]:
        L = st["learned"]; seen = f" ({L['prompts']} prompts, {L['generated']})" if L.get("generated") and L.get("prompts") else ""
        pat_rows.append(("label", clip(f" Patterns from your past chats{seen}  ·  i hides", W - 1)))
        cap = max(4, H // 3)
        body = [("blue", " " + w) for p in pats for w in wrap("• " + p, iw, "  ")]
        pat_rows += body[:cap] + ([("bluedim", " …")] if len(body) > cap else [])
    elif pats:
        skill = " · s installs a skill" if any(x.get("slug") for x in st["insights"]) else ""
        pat_rows.append(("blue", clip(f" {len(pats)} pattern{'s' if len(pats) != 1 else ''} from your past chats · i to read{skill}", W - 1)))
    elif st["review_running"]: pat_rows.append(("bluedim", clip(" Claude is analysing your past chats now…", W - 1)))
    elif st["ai"] and not st["learned"].get("generated"): pat_rows.append(("bluedim", clip(" Claude will analyse your past chats in the background", W - 1)))
    # the card first: it gets every row the header, patterns, footer and the two list rows do not need
    fixed = 1 + 1 + 1 + (1 + len(pat_rows) if pat_rows else 0) + 1            # header, rule, rule under the card, patterns + rule, footer
    min_list, pref_list = min(n, 2), (min(n, max(2, (H - 12) // 4)) if n else 0)
    room = max(H - 1 - fixed - ((1 + min_list) if n else 0), 3)               # the most rows the card can ever have
    if e is None:
        card = [("bluedim", "No prompts in this thread yet."), ("blank", ""), ("bluedim", "Send a prompt in Claude Code and it appears here."),
                *([("bluedim", w) for w in wrap("Analysis is off. Turn it on: " + coach.py_cmd("setup.py", "--panel-ai", "on"), iw, "  ")] if not st["ai"] else [])]
    else:                                                                      # shrink the improvements, never the enhanced prompt
        for level in ((1, 2) if narrow else (0, 1, 2)):
            card = card_lines(st, ui, i, e, iw, level)
            if len(card) <= room: break
    card_h = max(min(len(card), room), 3)
    list_n = min(pref_list, max(H - 1 - fixed - card_h - 1, min_list)) if n else 0   # leftover rows go to the list, up to its preferred size
    ui["cs"] = min(max(ui["cs"], 0), max(len(card) - card_h, 0))
    shown = card[ui["cs"]:ui["cs"] + card_h]
    if ui["cs"] > 0 and shown: shown[0] = ("meta", "▴ PgUp for the start")
    if ui["cs"] + card_h < len(card) and shown: shown[-1] = ("meta", "▾ PgDn for more")
    rows = [head, rule] + [c(k, (" " + t)[:W - 1]) if k != "blank" else "" for k, t in shown] + [""] * (card_h - len(shown))
    rows.append(rule)
    if pat_rows: rows += [c(k, t[:W - 1]) for k, t in pat_rows] + [rule]
    # the list
    if n:
        lo = ui["lo"]; lo = i if i < lo else (i - list_n + 1 if i >= lo + list_n else lo); lo = min(max(lo, 0), max(n - list_n, 0)); ui["lo"] = lo
        more = ("▴" if lo > 0 else " ") + ("▾" if lo + list_n < n else " ")
        rows.append(c("meta", f" Prompts in this thread  {more}"))
        sw = max(len(stamp(x["ts"])) for x in es[lo:lo + list_n])
        for idx in range(lo, lo + list_n):
            x = es[idx]; _s, glyph, gk, _w = status(x, st, ui)
            text = clip(x["text"], max(W - 8 - sw, 8))
            if idx == i: rows.append(c("sel", f" › {glyph} {stamp(x['ts']):<{sw}}  {text}".ljust(W - 1)[:W - 1]))
            else: rows.append(" " + "  " + c(gk, glyph) + " " + c("meta", f"{stamp(x['ts']):<{sw}}  ") + text)
    # footer: a message, or the keys that fit
    if ui["msg"]: rows.append(c("warn", (" " + ui["msg"])[:W - 1]))
    else: rows.append(" " + "  ".join(c("key", k) + " " + c("meta", lab) for k, lab in footer_text(W, False)))
    return rows[:H - 1]


def detail_frame(st, ui, i, e, W, H, color=True):
    """One prompt, full width, as plain text: what you wrote, what can be improved, the task and workflow, the ENHANCED PROMPT to copy."""
    def c(kind, s): return f"\033[{CODE[kind]}m{s}\033[0m" if color and CODE[kind] != "0" else s
    iw = max(min(W - 4, MAX_WIDTH), 20)
    L = [("label", "YOUR PROMPT")] + [("prompt", w) for w in wrap(e["text"], iw)] + [("blank", "")]
    adv = e["advice"]
    if adv:
        L += [("label", "CAN BE IMPROVED")] + [(k, w) for k, x in advisor.lines(adv, iw - 2) if k != "after" for w in [x]] + [("blank", "")]
        L += [(k, w) for k, x in e["disc"] for w in wrap(x, iw, "   ")] + ([("blank", "")] if e["disc"] else [])
    elif e["fixes"]:
        L += [("label", "CAN BE IMPROVED")] + [("blue", w) for f in e["fixes"] for w in wrap("• " + f.split(": ", 1)[1], iw, "  ")] + [("blank", "")]
    L.append(("label", "ENHANCED PROMPT" + ("   (press c to copy it; [ASK: ...] and <email> placeholders are yours to fill in)" if e["after"] else "")))
    if e["after"]:
        for ln in e["after"].splitlines(): L += [("enh", w) for w in wrap(ln, iw)]
    elif e["error"]: L.append(("bluedim", f"Analysis failed ({str(e['error'])[:80]}). Press e to try again."))
    elif e["off"]: L.append(("bluedim", "This project is in llm-off.txt, so it is never sent to Claude."))
    else: L.append(("bluedim", "None yet. Press e to have Claude write one for this prompt (sends this redacted prompt to your Claude subscription)."))
    body_h = H - 3
    ui["dscroll"] = min(max(ui["dscroll"], 0), max(len(L) - body_h, 0))
    rows = [c("title", " coachline") + c("meta", f"  prompt {i + 1} of {len(st['entries'])}  ·  {stamp(e['ts'])}")[:max(W - 10, 0)]]
    part = L[ui["dscroll"]:ui["dscroll"] + body_h]
    rows += [c(k, ("  " + x)[:W - 1]) if k != "blank" else "" for k, x in part] + [""] * (body_h - len(part))
    rows.append(c("warn", (" " + ui["msg"])[:W - 1]) if ui["msg"] else " " + "  ".join(c("key", k) + " " + c("meta", lab) for k, lab in footer_text(W, True)))
    return rows[:H - 1]


# ---------------------------------------------------------------- input
def handle(ui, st, key, io=None):
    """Apply one key to ui. True = quit. `io` (copy, enhance, review, install) is swapped for fakes in tests."""
    io = io or IO
    key = ALIASES.get(key, key); ui["msg"] = ""
    n = len(st["entries"]); i, e = cur_entry(ui, st)
    if key == "q": return True
    if key == "enter":
        if e is not None: ui["detail"] = not ui["detail"]; ui["dscroll"] = 0
        return False
    if key == "esc": ui["detail"] = False; return False
    if key == "patterns": ui["patterns"] = not ui["patterns"]; return False
    if key == "copy":
        if e is None: ui["msg"] = "no prompt selected"
        elif not e["after"]: ui["msg"] = "no enhanced prompt yet: press e to have Claude write one for this prompt"
        else:
            m = io.copy(e["after"])
            if m: ui["copied"][e["key"]] = time.time()
            ui["msg"] = f"copied the enhanced prompt ({len(e['after'])} characters) via {m}" if m else "no clipboard available here: press Enter and select the text"
        return False
    if key == "enhance":
        if e is None: ui["msg"] = "no prompt selected"
        elif e["after"]: ui["msg"] = "already analysed: press c to copy the enhanced prompt"
        elif e["off"]: ui["msg"] = "this project is in llm-off.txt: not sending it to Claude"
        elif time.time() - ui["pending"].get(e["key"], 0) < PENDING_SECONDS: ui["msg"] = "already asking Claude about this prompt..."
        else:
            io.enhance(e["key"]); ui["pending"][e["key"]] = time.time()
            ui["msg"] = "asking Claude in the background (about 20 seconds); the panel updates by itself"
        return False
    if key == "skill":
        slugs = [x["slug"] for x in st["insights"] if x.get("slug")]
        if not slugs: ui["msg"] = "no drafted skill to install yet (it appears after Claude analyses your past chats)"; return False
        ok, ui["msg"] = io.install(slugs[0])
        for x in st["insights"]:
            if ok and x.get("slug") == slugs[0]: x["installed"] = True; x["slug"] = None      # the pattern stops offering it at once
        return False
    if ui["detail"]:
        delta = {"up": -1, "down": 1, "pgup": -10, "pgdn": 10, "home": -10 ** 6, "end": 10 ** 6}.get(key)
        if delta is not None: ui["dscroll"] = max(0, ui["dscroll"] + delta)
        return False
    if key in ("up", "down", "home", "end") and n:
        j = {"up": i - 1, "down": i + 1, "home": 0, "end": n - 1}[key]
        j = min(max(j, 0), n - 1)
        ui["sel"] = None if j == n - 1 else j; ui["cs"] = 0                # the newest is "following": new prompts take over the card
    elif key in ("pgup", "pgdn"):
        ui["cs"] = max(0, ui["cs"] + (-6 if key == "pgup" else 6))
    return False


def autopilot(st, ui, io=None, now=None):
    """Start Claude's work in the background when analysis is on: this thread's newest unanalysed prompts (one at a time), and a
    review of your whole history when it is due. Returns what it started (for tests)."""
    io = io or IO; now = time.time() if now is None else now; acts = []
    if not st["ai"]: return acts
    ui["pending"] = {k: t for k, t in ui["pending"].items() if now - t < PENDING_SECONDS}
    if not ui["pending"]:                                        # one analysis at a time keeps your usage predictable
        todo = [e for e in st["entries"][-5:] if e["advisable"] and not e["off"] and not e["advice"] and not e["error"] and e["key"] not in ui["tried"]]
        if todo:
            key = todo[-1]["key"]; io.enhance(key); ui["pending"][key] = now; ui["tried"].add(key); acts.append(("enhance", key))
    if now >= ui["review_after"] and review_due(st, now):
        io.review(); ui["review_after"] = now + 1800; acts.append(("review",))
    return acts


def review_due(st, now):
    """True when Claude has not analysed your history yet, or it is 2+ days old and 15+ new prompts have piled up."""
    if st["review_running"]: return False
    gen = st["learned"].get("generated")
    if not gen: return True
    try: age = (now - dt.datetime.strptime(gen, "%Y-%m-%d").timestamp()) / 86400
    except ValueError: return True
    return age >= 2 and review.count_prompts(coach.HIST) - st["learned"].get("history_prompts", 0) >= 15


def read_key(timeout):
    """One key name ('up', 'q', 'j', ...) or None on timeout. Stdlib only: msvcrt on Windows, termios elsewhere."""
    if os.name == "nt":
        import msvcrt
        end = time.time() + timeout
        while time.time() < end:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                return WIN_KEYS.get(msvcrt.getwch()) if ch in ("\x00", "\xe0") else ch
            time.sleep(0.03)
        return None
    import select
    fd = sys.stdin.fileno()
    if not select.select([fd], [], [], timeout)[0]: return None
    ch = os.read(fd, 1).decode("utf-8", "ignore")
    if ch != "\x1b": return ch
    seq = ""
    while len(seq) < 3 and select.select([fd], [], [], 0.03)[0]: seq += os.read(fd, 1).decode("utf-8", "ignore")
    return POSIX_KEYS.get(seq, "esc")


def beat(last=[0.0]):
    """Tell launch.py a panel is open (at most one write per second)."""
    if time.time() - last[0] >= 1:
        last[0] = time.time()
        try:
            os.makedirs(coach.STATE, exist_ok=True)
            with open(coach.ALIVE, "w") as f: f.write(str(last[0]))
        except OSError: pass


def loop(next_key, write, size, load_state, clock=time.time, reload_every=2.0, stop=lambda: False, heartbeat=lambda: None, io=None, work=None):
    """Draw only when something changed: a key, a new size, or new data. next_key(timeout) -> key|None.
    work(st, ui) runs at start and on every data reload (the panel's own Claude jobs)."""
    ui = new_ui(); st = load_state(); last_load = clock(); last_size = None; dirty = True
    if work: work(st, ui)
    while not stop():
        heartbeat()
        W, H = size()
        if dirty or (W, H) != last_size:
            write(render(st, ui, W, H)); last_size = (W, H); dirty = False
        k = next_key(0.25)
        if k is None:
            if clock() - last_load >= reload_every:
                new = load_state(); last_load = clock()
                if signature(new) != signature(st): st = new; dirty = True
                if work: work(st, ui)
            continue
        if handle(ui, st, k, io): return
        dirty = True


def main(argv):
    ap = argparse.ArgumentParser(); ap.add_argument("--history", default=coach.HIST)
    ap.add_argument("--exit-after", type=float, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--once", action="store_true"); ap.add_argument("--width", type=int); ap.add_argument("--height", type=int)
    ap.add_argument("--patterns", action="store_true", help="with --once: show the patterns from your past chats expanded")
    a = ap.parse_args(argv)
    if a.once or not (sys.stdin.isatty() and sys.stdout.isatty()):
        if not a.once: print("(not a terminal: printing one frame; run watch.py in a real terminal pane for the interactive view)")
        ui = new_ui(); ui["patterns"] = a.patterns
        print("\n".join(render(build(a.history), ui, a.width or 100, a.height or 40, color=False))); return
    if os.name == "nt": os.system("")  # switches the Windows console to ANSI mode
    else:
        import termios, tty
        fd = sys.stdin.fileno(); old = termios.tcgetattr(fd); tty.setcbreak(fd)
    sys.stdout.write("\033[?1049h\033[?25l"); t0 = time.time()
    try:
        loop(read_key, lambda rows: (sys.stdout.write("\033[H" + "\033[K\n".join(rows) + "\033[K\033[J"), sys.stdout.flush()),
             lambda: (a.width or shutil.get_terminal_size((100, 30)).columns, a.height or shutil.get_terminal_size((100, 30)).lines),
             lambda: build(a.history), stop=lambda: bool(a.exit_after) and time.time() - t0 > a.exit_after, heartbeat=beat,
             work=lambda st, ui: autopilot(st, ui))
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h\033[?1049l"); sys.stdout.flush()
        try: os.remove(coach.ALIVE)
        except OSError: pass
        if os.name != "nt": termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
