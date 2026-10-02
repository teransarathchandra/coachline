"""watch.py - the coachline panel: THIS THREAD only, one column, analysed by Claude. No animation.

Top: the prompt you are looking at (the newest by default) in white, then what can be improved in blue, then the
ENHANCED PROMPT, with a Copy button. Below: one line of patterns Claude found in your past chats (`i` to read) and a compact
list of this thread's prompts with a status glyph each.

Keyboard                                                   Mouse (turn off with m, to select text with the mouse)
  Up / Down (k / j, p / n)  select an earlier / later prompt   wheel over the list   select a prompt
  g / G                     oldest / newest                    wheel over the card   scroll the card
  PgUp / PgDn (b / space)   scroll the card                    click a prompt        select it
  Enter                     the prompt full width (Esc closes) click a button        c Copy, e Analyse, Enter Full, ...
  c  copy the enhanced prompt exactly as written
  e  have Claude analyse the selected prompt now
  i  read / hide the patterns from your past chats
  s  install the skill Claude drafted for a request you keep repeating (never overwrites)
  m  mouse on / off          q or Ctrl+C  quit

  python watch.py            interactive
  python watch.py --once     print one plain frame and exit (also used when stdin is not a terminal)

Status glyphs: ✓ analysed   … analysing or queued   ! can be improved (local hints)   × analysis failed   – opted out   · nothing to add

With Claude analysis on (setup.py --panel-ai on) the panel itself starts the background `claude -p` jobs on your subscription:
the newest unanalysed prompts of this thread, and a review of your history every ~2 days. Redacted; llm-off.txt projects never sent.
The screen redraws only on a key, a click or when new data arrives.
"""
import argparse, datetime as dt, glob, json, os, re, sys, time, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import advisor
import coach
import discover
import memory
import review

POSIX_KEYS = {"[A": "up", "[B": "down", "[5~": "pgup", "[6~": "pgdn", "[H": "home", "[F": "end", "[1~": "home", "[4~": "end",
              "OA": "up", "OB": "down", "OH": "home", "OF": "end"}
WIN_KEYS = {"H": "up", "P": "down", "I": "pgup", "Q": "pgdn", "G": "home", "O": "end"}     # msvcrt fallback when VT input is unavailable
ALIASES = {"k": "up", "j": "down", "p": "up", "n": "down", "b": "pgup", " ": "pgdn", "g": "home", "G": "end", "\x03": "q", "Q": "q",
           "c": "copy", "e": "enhance", "s": "skill", "i": "patterns", "m": "mouse", "\r": "enter", "\n": "enter", "\x1b": "esc",
           "x": "dismiss", "a": "adopt", "r": "research"}
IO = type("IO", (), {"copy": staticmethod(coach.copy_text), "enhance": staticmethod(coach.spawn_key),
                     "review": staticmethod(coach.spawn_review), "install": staticmethod(review.install_skill),
                     "mark": staticmethod(memory.mark), "research": staticmethod(coach.spawn_research)})  # swapped for fakes in tests
# your words white; what can be improved blue (bright blue reads on dark and light terminals); structure in grey
CODE = {"title": "1", "meta": "90", "prompt": "1;97", "label": "1;94", "blue": "94", "bluedim": "2;94", "enh": "94", "rule": "90", "blank": "0",
        "ok": "92", "warn": "93", "bad": "91", "key": "1;97", "task": "2;94", "better": "1;94", "src": "2;94", "dim": "2;94", "use": "94",
        "get": "94", "tip": "94", "flow": "2;94", "head": "1;94", "after": "94", "sel": "7", "chip": "1;97;44", "brand": "1;97;44",
        "g_prompt": "97", "g_improve": "94", "g_enh": "1;94", "g_web": "2;94", "g_info": "90",
        "h_prompt": "1;97", "h_improve": "1;94", "h_enh": "1;94", "h_web": "1;94", "h_info": "90"}
PENDING_SECONDS = 150
MAX_WIDTH = 100                      # lines longer than this are hard to read, however wide the pane is
GLYPHS = {"done": ("✓", "ok"), "pending": ("…", "warn"), "error": ("×", "bad"), "off": ("–", "meta"),
          "local": ("!", "blue"), "quiet": ("·", "meta")}
MOUSE_ON, MOUSE_OFF = "\033[?1000h\033[?1006h", "\033[?1000l\033[?1006l"      # button presses + wheel, SGR coordinates (any column)


# ---------------------------------------------------------------- text width: wide characters (CJK, emoji) take two columns
def cw(ch):
    o = ord(ch)
    if o < 32 or 0x7f <= o < 0xa0: return 0
    if unicodedata.category(ch) in ("Mn", "Me", "Cf") or unicodedata.combining(ch): return 0
    if unicodedata.east_asian_width(ch) in ("W", "F") or 0x1F300 <= o <= 0x1FAFF: return 2
    return 1


def dw(s):
    return sum(cw(c) for c in s)


def tidy(s):
    """One line of plain text: control characters and tabs become spaces."""
    return re.sub(r"[\x00-\x1f\x7f-\x9f]+", " ", s)


def fit(s, w):
    """Hard cut to w columns (no ellipsis)."""
    out, n = [], 0
    for c in s:
        n += cw(c)
        if n > w: break
        out.append(c)
    return "".join(out)


def clip(s, w):
    """s in at most w columns, ending in an ellipsis when it was cut."""
    if dw(s) <= w: return s
    return fit(s, max(w - 1, 0)) + "…"


def pad(s, w):
    return s + " " * max(w - dw(s), 0)


def wrap(s, w, indent=""):
    """Greedy word wrap by display width; a word longer than a line is broken. Never returns []."""
    w = max(w, 8); lines, cur = [], ""
    for word in s.split(" "):
        cand = word if not cur else cur + " " + word
        if dw(cand) <= w: cur = cand; continue
        if cur: lines.append(cur); cur = indent + word
        else: cur = word
        while dw(cur) > w:
            head = fit(cur, w); lines.append(head); cur = indent + cur[len(head):]
    lines.append(cur)
    return lines


def bullet(s, w):
    """'• text' wrapped with a hanging indent. Never cut: the improvements are what you came to read."""
    return wrap("• " + s, w, "  ")


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


def current_session(rows):
    """The conversation you are in: whichever happened last, the SessionStart hook announcing a session (a fresh one has no prompt and no
    transcript yet) or a recent session's transcript being written (a resumed one, or a prompt sent).
    The newest history line is not enough. Resuming (or /clear, /exit) logs a command under a throwaway session id, and a resumed
    session logs nothing until you send a prompt, yet Claude Code writes to its transcript the moment it resumes.
    With neither to go on (a fresh install), the newest prompt that is not a /command."""
    seen, ids = set(), []
    for r in reversed(rows):
        if r[3] and r[3] not in seen: seen.add(r[3]); ids.append(r[3])
    best = None
    for sid in ids[:40]:
        for p in glob.glob(os.path.join(coach.CONFIG, "projects", "*", sid + ".jsonl")):
            try: m = os.path.getmtime(p)
            except OSError: continue
            if best is None or m > best[0]: best = (m, sid)
    started = coach.started_session()
    if started and (not best or started[1] >= best[0]): return started[0]
    if best: return best[1]
    for r in reversed(rows):
        if not r[2].lstrip().startswith("/"): return r[3]
    return rows[-1][3]


def build(path, session=None, notice=True):
    """State for render(): THIS thread's prompts (the session you are in, see current_session, or `session` when the caller knows it,
    as the Claude Code pane does) plus what Claude knows from the rest."""
    rows = load_full(path); aft = rewrites(); L = coach.learned()
    st = {"entries": [], "insights": [], "learned": L, "ai": coach.ai_on(), "review_running": review_running(), "total": 0, "session": None, "notice": None,
          "research_paused": None}
    if not rows: st["session"] = session; return st
    cur = st["session"] = session or current_session(rows); prev = None
    mem = memory.statuses()
    for ts, proj, text, sid in rows:
        gap = None if prev is None else ts - prev; prev = ts
        if sid != cur or not coach.scorable(text) or text.startswith("/coach"): continue
        fails = [n for n, fn in coach.RULES if not fn(text, gap)]
        key = coach.prompt_key((ts, proj, text)); rec = aft.get(key) or {}; adv = rec.get("advice") or {}
        after = adv.get("after") or (re.sub(r"^AFTER:\s*", "", rec.get("text", "")).strip() if rec.get("text") else "")
        items = [dict(x, status=mem.get(memory.item_id(x))) for x in rec.get("discovery") or []
                 if isinstance(x, dict) and x.get("url") and mem.get(memory.item_id(x)) != "dismissed"]
        refs = discover.references(items) if after else ""
        st["entries"].append({"ts": ts, "key": key, "text": tidy(coach.redact(text))[:2000], "fails": fails,
                              "fixes": [f"{n}: {coach.FIX[n]}" for n in fails], "advice": adv, "after": after + ("\n\n" + refs if refs else ""),
                              "refs": bool(refs), "items": items, "disc": discover.lines(items, 200, numbered=True),
                              "error": None if adv else rec.get("error"), "off": coach.llm_off(proj), "advisable": coach.advisable(text, fails)})
    st["research_paused"] = discover.paused_until() if st["ai"] else None
    st["insights"] = insights(st["entries"], rows, L)
    st["notice"] = coach.notice(cur) if notice and cur else None
    return st


def signature(st):
    return (st.get("session"), len(st["entries"]), sum(bool(e["advice"]) + bool(e["error"]) for e in st["entries"]), len(st["insights"]),
            st["learned"].get("generated"), st["review_running"], st["ai"], sum(len(e.get("items", [])) for e in st["entries"]),
            st.get("research_paused"))


# ---------------------------------------------------------------- presentation helpers
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


def card_lines(st, ui, i, e, iw, acts=False):
    """[(section, kind, text, right, action)]: the prompt you are looking at, what to improve, the enhanced prompt.
    section picks the gutter colour; kind 'head' is a section title with an optional right-hand label (a button when it has an action).
    Nothing in Improve is ever dropped or cut. When the card is taller than the pane the enhanced prompt, which is last, scrolls (PgDn, wheel)."""
    out = []
    _s, glyph, kind, words = status(e, st, ui)
    older = ui["sel"] is not None and i != len(st["entries"]) - 1
    out.append(("prompt", "head", "Your prompt", f"{stamp(e['ts'])} · {glyph} {words}" + (" · earlier prompt, G = newest" if older else ""), None))
    pl = wrap(e["text"], iw)
    cut = len(pl) > 5
    if cut: pl = pl[:5]; pl[-1] = clip(pl[-1] + " ", iw - 1) + "…"
    out += [("prompt", "prompt", w, "", None) for w in pl] + ([("prompt", "meta", "Enter shows the whole prompt", "", "enter")] if cut else [])
    adv = e["advice"]
    if adv:
        bullets = list(adv.get("tips", []))
        bullets += [f"use /{u['name']}" + (f": {u['why']}" if u.get("why") else "") for u in adv.get("use", [])]
        bullets += [f"get {g['name']}" + (f": {g['why']}" if g.get("why") else "") for g in adv.get("get", [])]
        if bullets:
            out += [("", "blank", "", "", None), ("improve", "head", "Improve", adv.get("task", ""), None)]
            if adv.get("summary"): out += [("improve", "task", w, "", None) for w in wrap(adv["summary"], iw)]
            for b in bullets: out += [("improve", "blue", w, "", None) for w in bullet(b, iw)]
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
        return out + notice_lines(st, iw)
    out.append(("", "blank", "", "", None))
    if e["error"]:
        out.append(("info", "head", "Analysis failed", "", None))
        out.append(("info", "bluedim", f"Claude's analysis failed ({str(e['error'])[:80]}). Press e to try again.", "", "enhance"))
        return out + notice_lines(st, iw)
    if e["off"]:
        out.append(("info", "bluedim", "This project is in llm-off.txt, so it is never sent to Claude.", "", None))
        return out + notice_lines(st, iw)
    if kind == "warn":
        out.append(("info", "head", "Analysing", "", None))
        out.append(("info", "bluedim", "Claude is analysing this prompt, usually about 20 seconds. This updates by itself.", "", None))
    hints = [f.split(": ", 1)[1] for f in e["fixes"]]
    if hints:
        out.append(("improve", "head", "While you wait" if kind == "warn" else "Improve", "", None))
        for h in hints: out += [("improve", "blue", w, "", None) for w in bullet(h, iw)]
    elif kind != "warn":
        out.append(("info", "bluedim", "Nothing to improve here.", "", None))
    if not st["ai"]:
        out.append(("", "blank", "", "", None))
        out.append(("info", "bluedim", "Press e for Claude's analysis and an enhanced prompt.", "", "enhance"))
        out += [("info", "bluedim", w, "", None) for w in wrap("Analyse every prompt automatically: " + coach.py_cmd("setup.py", "--panel-ai", "on"), iw, "  ")]
    return out + notice_lines(st, iw)


def notice_lines(st, iw):
    """The first-run notice (coach.notice), last on the card."""
    if not st.get("notice"): return []
    return [("", "blank", "", "", None)] + [("info", "bluedim", w, "", None) for w in wrap(st["notice"], iw)]


# ---------------------------------------------------------------- rendering
def new_ui():
    return {"sel": None, "lo": 0, "cs": 0, "detail": False, "dscroll": 0, "pending": {}, "tried": set(), "review_after": 0.0, "msg": "",
            "patterns": False, "copied": {}, "mouse": True, "hits": [], "list_rows": None}


FOOT = [("↑↓", "prompt", None), ("c", "copy", "copy"), ("e", "analyse", "enhance"), ("Enter", "full", "enter"),
        ("i", "patterns", "patterns"), ("s", "skill", "skill"), ("q", "quit", "q"), ("m", "mouse", "mouse")]
FOOT_DETAIL = [("Esc", "back", "esc"), ("c", "copy", "copy"), ("e", "analyse", "enhance"), ("↑↓", "scroll", None), ("q", "quit", "q"), ("m", "mouse", "mouse")]
PRIORITY = ["↑↓", "c", "q", "Esc", "e", "Enter", "i", "s", "m"]       # what a narrow footer keeps, most important first


def footer_row(W, items, P, hits, row):
    """The key hints as buttons that fit the width, least important dropped first, still in reading order. Records their click areas."""
    chosen, used = set(), 1
    for key in sorted((it[0] for it in items), key=lambda k: PRIORITY.index(k) if k in PRIORITY else 99):
        it = next(x for x in items if x[0] == key)
        need = dw(it[0]) + 1 + dw(it[1]) + (2 if chosen else 0)
        if used + need > W - 1: continue
        chosen.add(key); used += need
    out, col = " ", 1
    for key, label, act in items:
        if key not in chosen: continue
        if col > 1: out += "  "; col += 2
        w = dw(key) + 1 + dw(label)
        if act: hits.append((row, col, col + w, act))
        out += P("key", key) + " " + P("meta", label); col += w
    return out


def render(st, ui, W, H, color=True):
    """The frame as a list of lines. Click areas are recorded in ui['hits'] as (row, col0, col1, action | prompt index)."""
    def P(kind, s): return f"\033[{CODE[kind]}m{s}\033[0m" if color and CODE[kind] != "0" and s else s
    W = max(W, 30); H = max(H, 10)
    hits = ui["hits"] = []; ui["list_rows"] = None
    i, e = cur_entry(ui, st)
    if ui["detail"] and e is not None: return detail_frame(st, ui, i, e, W, H, color)
    iw = min(W - 4, MAX_WIDTH)
    es = st["entries"]; n = len(es)
    # header: where you are, and whether Claude is on
    working = st["review_running"] or any(status(x, st, ui)[0] == "pending" for x in es)
    word, kind, dot = (("Claude off", "meta", "○") if not st["ai"] else ("Claude working…", "warn", "●") if working else ("Claude on", "ok", "●"))
    left = f" · this thread · {n} prompt{'s' if n != 1 else ''}"
    right = f"{dot} {word} "
    if 11 + dw(left) + dw(right) + 1 > W - 1: left = ""
    if 11 + dw(left) + dw(right) + 1 > W - 1: right = f"{dot} "
    head = " " + P("brand", " coachline") + P("meta", left) + " " * max(W - 1 - 11 - dw(left) - dw(right), 1) + P(kind, right)
    rule = P("rule", " " + "─" * (W - 3))
    # patterns: one line, or the list when expanded
    pats = pattern_texts(st); pat_rows = []
    if pats and ui["patterns"]:
        L = st["learned"]; seen = f" ({L['prompts']} prompts, {L['generated']})" if L.get("generated") and L.get("prompts") else ""
        pat_rows.append(("label", clip(f" Patterns from your past chats{seen}  ·  i hides", W - 1), "patterns"))
        cap = max(4, H // 3)
        body = [("blue", " " + w, None) for p in pats for w in wrap("• " + p, iw, "  ")]
        pat_rows += body[:cap] + ([("bluedim", " …", None)] if len(body) > cap else [])
    elif pats:
        skill = " · s installs a skill" if any(x.get("slug") for x in st["insights"]) else ""
        pat_rows.append(("blue", clip(f" {len(pats)} pattern{'s' if len(pats) != 1 else ''} from your past chats · i to read{skill}", W - 1), "patterns"))
    elif st["review_running"]: pat_rows.append(("bluedim", clip(" Claude is analysing your past chats now…", W - 1), None))
    elif st["ai"] and not st["learned"].get("generated"): pat_rows.append(("bluedim", clip(" Claude will analyse your past chats in the background", W - 1), None))
    # the card first: it gets every row the header, patterns, footer and the two list rows do not need
    fixed = 1 + 1 + 1 + (1 + len(pat_rows) if pat_rows else 0) + 1            # header, rule, rule under the card, patterns + rule, footer
    min_list, pref_list = min(n, 2), (min(n, max(2, (H - 12) // 4)) if n else 0)
    room = max(H - 1 - fixed - ((1 + min_list) if n else 0), 3)               # the most rows the card can ever have
    if e is None:
        card = [("info", "bluedim", "No prompts in this thread yet.", "", None), ("", "blank", "", "", None),
                ("info", "bluedim", "Send a prompt in Claude Code and it appears here.", "", None),
                *[("info", "bluedim", w, "", None) for w in (wrap("Analysis is off. Turn it on: " + coach.py_cmd("setup.py", "--panel-ai", "on"), iw, "  ") if not st["ai"] else [])]]
    else:
        card = card_lines(st, ui, i, e, iw)
    card_h = max(min(len(card), room), 3)
    list_n = min(pref_list, max(H - 1 - fixed - card_h - 1, min_list)) if n else 0   # leftover rows go to the list, up to its preferred size
    ui["cs"] = min(max(ui["cs"], 0), max(len(card) - card_h, 0))
    shown = list(card[ui["cs"]:ui["cs"] + card_h])
    if ui["cs"] > 0 and shown: shown[0] = ("", "meta", "▴ PgUp for the start", "", "pgup")
    if ui["cs"] + card_h < len(card) and shown: shown[-1] = ("", "meta", "▾ PgDn for more", "", "pgdn")
    rows = [head, rule]
    for sect, k, text, rt, act in shown:
        r = len(rows)
        if k == "blank": rows.append(""); continue
        if not sect:                                                             # an indicator row, no gutter
            rows.append(" " + P(k, fit(text, W - 2)))
            if act: hits.append((r, 1, 1 + min(dw(text), W - 2), act))
            continue
        avail = W - 4; lead = " " + P("g_" + sect, "┃") + " "
        if k == "head":
            title = P("h_" + sect, text)
            if rt:
                rt = clip(rt, max(avail - dw(text) - 3, 4)); rw = dw(rt) + (2 if act else 0); gap = max(avail - dw(text) - rw, 1)
                chip = P("chip", f" {rt} ") if act else P("meta", rt)
                if act: hits.append((r, 3 + dw(text) + gap, 3 + dw(text) + gap + rw, act))
                rows.append(lead + title + " " * gap + chip)
            else: rows.append(lead + title)
            continue
        t = fit(text, avail)
        rows.append(lead + P(k, t))
        if act: hits.append((r, 3, 3 + dw(t), act))
    while len(rows) < 2 + card_h: rows.append("")
    rows.append(rule)
    for k, t, act in pat_rows:
        if act: hits.append((len(rows), 0, dw(t), act))
        rows.append(P(k, t))
    if pat_rows: rows.append(rule)
    # the list
    if n:
        lo = ui["lo"]; lo = i if i < lo else (i - list_n + 1 if i >= lo + list_n else lo); lo = min(max(lo, 0), max(n - list_n, 0)); ui["lo"] = lo
        more = ("▴" if lo > 0 else " ") + ("▾" if lo + list_n < n else " ")
        rows.append(P("meta", f" Prompts in this thread  {more}"))
        ui["list_rows"] = (len(rows), len(rows) + list_n)
        sw = max(len(stamp(x["ts"])) for x in es[lo:lo + list_n])
        for idx in range(lo, lo + list_n):
            x = es[idx]; _s, glyph, gk, _w = status(x, st, ui)
            text = clip(x["text"], max(W - 8 - sw, 8))
            hits.append((len(rows), 0, W - 1, idx))
            if idx == i: rows.append(P("sel", pad(f" › {glyph} {stamp(x['ts']):<{sw}}  {text}", W - 1)))
            else: rows.append("   " + P(gk, glyph) + " " + P("meta", f"{stamp(x['ts']):<{sw}}  ") + text)
    # footer: a message, or the keys that fit (as clickable buttons)
    rows.append(P("warn", fit(" " + ui["msg"], W - 1)) if ui["msg"] else footer_row(W, FOOT, P, hits, len(rows)))
    return rows[:H - 1]


def detail_frame(st, ui, i, e, W, H, color=True):
    """One prompt, full width, as plain text: what you wrote, what can be improved, the task and workflow, the ENHANCED PROMPT to copy."""
    def P(kind, s): return f"\033[{CODE[kind]}m{s}\033[0m" if color and CODE[kind] != "0" and s else s
    iw = max(min(W - 4, MAX_WIDTH), 20)
    L = [("label", "YOUR PROMPT")] + [("prompt", w) for w in wrap(e["text"], iw)] + [("blank", "")]
    adv = e["advice"]
    if adv:
        L += [("label", "CAN BE IMPROVED")] + [(k, w) for k, x in advisor.lines(adv, iw - 2) if k != "after" for w in wrap(x, iw - 2, "   ")] + [("blank", "")]
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
    rows = [" " + P("brand", " coachline ") + P("meta", fit(f"  prompt {i + 1} of {len(st['entries'])}  ·  {stamp(e['ts'])}", max(W - 14, 0)))]
    part = L[ui["dscroll"]:ui["dscroll"] + body_h]
    rows += [P(k, "  " + fit(x, W - 3)) if k != "blank" else "" for k, x in part] + [""] * (body_h - len(part))
    rows.append(P("warn", fit(" " + ui["msg"], W - 1)) if ui["msg"] else footer_row(W, FOOT_DETAIL, P, ui["hits"], len(rows)))
    return rows[:H - 1]


# ---------------------------------------------------------------- input
class InputParser:
    """Raw terminal input -> keys ('up', 'q', 'x', ...) and mouse events ('mouse', button, col, row, pressed).
    Input can arrive in pieces (a mouse report split across reads), so an unfinished escape sequence waits in buf for the next feed()."""
    def __init__(self): self.buf = ""

    def feed(self, s):
        b = self.buf + s; out, i, n = [], 0, len(b)
        while i < n:
            ch = b[i]
            if ch != "\x1b": out.append(ch); i += 1; continue
            if i + 1 >= n: break                                              # maybe the start of a sequence: wait for more
            nx = b[i + 1]
            if nx == "[":
                j = i + 2
                while j < n and not ("@" <= b[j] <= "~"): j += 1
                if j >= n: break
                body, fin = b[i + 2:j], b[j]; i = j + 1
                if body.startswith("<") and fin in "Mm":
                    try: bt, x, y = (int(v) for v in body[1:].split(";"))
                    except ValueError: continue
                    out.append(("mouse", bt, x, y, fin == "M"))
                elif "[" + body + fin in POSIX_KEYS: out.append(POSIX_KEYS["[" + body + fin])
            elif nx == "O":
                if i + 2 >= n: break
                k = POSIX_KEYS.get("O" + b[i + 2]); i += 3
                if k: out.append(k)
            else: out.append("\x1b"); i += 1
        self.buf = b[i:]
        return out

    def flush(self):
        """No more input is coming: a lone ESC was the Escape key; anything else unfinished is dropped."""
        t, self.buf = self.buf, ""
        return ["\x1b"] if t == "\x1b" else []


def parse_input(s):
    p = InputParser(); return p.feed(s) + p.flush()


def _click(ui, st, key, io):
    """A mouse event: wheel scrolls the list (selects) or the card; a left click presses the button or selects the prompt under it."""
    _m, b, x, y, press = key; r, c = y - 1, x - 1
    if b in (64, 65):
        if not press: return False                                            # only the press of a wheel notch counts
        d = -1 if b == 64 else 1; lr = ui.get("list_rows")
        if ui["detail"]: ui["dscroll"] = max(0, ui["dscroll"] + 3 * d)
        elif lr and lr[0] <= r < lr[1]: return handle(ui, st, "up" if d < 0 else "down", io)
        else: ui["cs"] = max(0, ui["cs"] + 3 * d)
        return False
    if b == 0 and press:
        for row, c0, c1, act in ui.get("hits", []):
            if row == r and c0 <= c < c1:
                if isinstance(act, int):
                    n = len(st["entries"]); ui["sel"] = None if act >= n - 1 else act; ui["cs"] = 0; ui["detail"] = False
                    return False
                return handle(ui, st, act, io)
    return False


def _mark(ui, it, action, io):
    status = "dismissed" if action == "dismiss" else "adopted"
    if io.mark(memory.item_id(it), status):
        ui["reload"] = True                                                   # the card and the copy drop it now, not on the next reload
        ui["msg"] = (f"hidden: {it['name']} will not be suggested again" if status == "dismissed"
                     else f"noted: you use {it['name']}; it will not be suggested again")
    else:
        ui["msg"] = "could not save that choice (see /coach doctor)"
    return False


def handle(ui, st, key, io=None):
    """Apply one key or mouse event to ui. True = quit. `io` (copy, enhance, review, install) is swapped for fakes in tests."""
    io = io or IO
    if isinstance(key, tuple): ui["msg"] = ""; return _click(ui, st, key, io)
    key = ALIASES.get(key, key); ui["msg"] = ""
    n = len(st["entries"]); i, e = cur_entry(ui, st)
    pick, ui["pick"] = ui.get("pick"), None
    if pick:                                                                  # x or a asked "which one?": a number answers, anything else cancels
        its = e["items"] if e else []
        if isinstance(key, str) and key.isdigit() and 1 <= int(key) <= len(its): return _mark(ui, its[int(key) - 1], pick, io)
        ui["msg"] = "cancelled"
        return False
    if key == "q": return True
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
    if key == "enter":
        if e is not None: ui["detail"] = not ui["detail"]; ui["dscroll"] = 0
        return False
    if key == "esc": ui["detail"] = False; return False
    if key == "patterns": ui["patterns"] = not ui["patterns"]; return False
    if key == "mouse":
        ui["mouse"] = not ui["mouse"]; ui["emit"] = MOUSE_ON if ui["mouse"] else MOUSE_OFF
        ui["msg"] = "mouse on: wheel scrolls, click selects (m turns it off)" if ui["mouse"] else "mouse off: select and copy text with the mouse (m turns it on)"
        return False
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


def term_size():
    """(columns, rows) of the terminal this panel is drawn in, asked of the terminal itself.
    Never the COLUMNS / LINES environment variables: a pane inherits them from the process that opened it (Claude Code's hook), so they
    describe some other window, and lines drawn for that width are cut mid-word by the real, narrower pane."""
    for f in (sys.__stdout__, sys.__stdin__, sys.__stderr__):
        try: s = os.get_terminal_size(f.fileno())
        except (OSError, ValueError, AttributeError): continue
        if s.columns > 0 and s.lines > 0: return s.columns, s.lines
    if os.name == "nt":                                                   # the console behind the handles, when they are redirected
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.windll.kernel32; k.CreateFileW.restype = wintypes.HANDLE
            h = k.CreateFileW("CONOUT$", 0xC0000000, 3, None, 3, 0, None)
            info = ctypes.create_string_buffer(22)
            if k.GetConsoleScreenBufferInfo(h, info):
                import struct
                l, t, r, b = struct.unpack("<hhhh", info.raw[10:18]); return r - l + 1, b - t + 1
        except (OSError, ImportError, AttributeError, ValueError): pass
    else:
        try:
            fd = os.open("/dev/tty", os.O_RDONLY)
            try: s = os.get_terminal_size(fd)
            finally: os.close(fd)
            return s.columns, s.lines
        except OSError: pass
    return 80, 24


_events = []           # parsed events not yet returned by read_key
_parser = InputParser()
_win = {}              # Windows: the VT-input reader thread's queue and console state


def _win_start():
    """Windows: put the console in VT input mode (arrows, mouse and Ctrl+C arrive as escape sequences, like on POSIX) and read it in a
    thread. Returns False when the console cannot do that; read_key then falls back to msvcrt (keyboard only)."""
    import ctypes, queue, threading
    from ctypes import wintypes
    k = ctypes.windll.kernel32; k.GetStdHandle.restype = wintypes.HANDLE
    h = k.GetStdHandle(-10); mode = wintypes.DWORD()
    if not k.GetConsoleMode(h, ctypes.byref(mode)): return False
    old = mode.value
    # no processed input (Ctrl+C arrives as a key), no line input or echo, no quick-edit (it would swallow clicks); VT input on
    if not k.SetConsoleMode(h, (old & ~(0x1 | 0x2 | 0x4 | 0x8 | 0x10 | 0x40)) | 0x80 | 0x200): return False
    q = queue.Queue()

    def run():
        buf = ctypes.create_unicode_buffer(512); n = wintypes.DWORD()
        while k.ReadConsoleW(h, buf, 511, ctypes.byref(n), None) and n.value: q.put(buf.value[:n.value])
    threading.Thread(target=run, daemon=True).start()
    _win.update(q=q, k=k, h=h, old=old)
    return True


def _win_stop():
    if _win: _win["k"].SetConsoleMode(_win["h"], _win["old"]); _win.clear()


def _raw(timeout):
    """The next chunk of raw input, or None after timeout."""
    if os.name == "nt":
        import queue
        try: return _win["q"].get(timeout=timeout)
        except queue.Empty: return None
    import select
    fd = sys.stdin.fileno()
    if not select.select([fd], [], [], timeout)[0]: return None
    return os.read(fd, 1024).decode("utf-8", "ignore")


def _msvcrt_key(timeout):
    import msvcrt
    end = time.time() + timeout
    while time.time() < end:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            return WIN_KEYS.get(msvcrt.getwch()) if ch in ("\x00", "\xe0") else ch
        time.sleep(0.03)
    return None


def read_key(timeout):
    """One key name ('up', 'q', 'j', ...) or mouse event, or None on timeout. Stdlib only: termios on POSIX, a VT-input
    reader thread on Windows (msvcrt, keyboard only, if the console cannot do that)."""
    if _events: return _events.pop(0)
    if os.name == "nt" and not _win: return _msvcrt_key(timeout)
    raw = _raw(0.05 if _parser.buf else timeout)                  # a half-received sequence gets a moment to finish, then a lone ESC is Escape
    ev = _parser.feed(raw) if raw else _parser.flush()
    _events.extend(ev[1:])
    return ev[0] if ev else None


def mark_shown(session, last=[None]):
    """Which session this panel shows, so the Claude Code pane (pane.py) of ANOTHER session still does its own background work."""
    if session == last[0]: return
    last[0] = session
    try:
        os.makedirs(coach.STATE, exist_ok=True)
        with open(os.path.join(coach.STATE, "watch.session"), "w", encoding="utf-8") as f: f.write(session or "")
    except OSError: pass


def beat(last=[0.0]):
    """Tell launch.py a panel is open (at most one write per second)."""
    if time.time() - last[0] >= 1:
        last[0] = time.time()
        try:
            os.makedirs(coach.STATE, exist_ok=True)
            with open(coach.ALIVE, "w") as f: f.write(str(last[0]))
        except OSError: pass


def loop(next_key, write, size, load_state, clock=time.time, reload_every=2.0, stop=lambda: False, heartbeat=lambda: None, io=None, work=None,
         emit=lambda s: None):
    """Draw only when something changed: a key, a click, a new size, or new data. next_key(timeout) -> key|mouse event|None.
    work(st, ui) runs at start and on every data reload (the panel's own Claude jobs). emit(s) writes control sequences (mouse on/off)."""
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
                if signature(new) != signature(st):
                    if new.get("session") != st.get("session"): ui.update(sel=None, lo=0, cs=0, detail=False, dscroll=0)      # another conversation: start at its newest prompt
                    st = new; dirty = True
                if work: work(st, ui)
            continue
        if handle(ui, st, k, io): return
        if ui.pop("reload", False): st = load_state(); last_load = clock()
        seq = ui.pop("emit", None)
        if seq: emit(seq)
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
    if os.name == "nt":
        os.system("")  # switches the Windows console to ANSI mode
        _win_start()
    else:
        import termios, tty
        fd = sys.stdin.fileno(); old = termios.tcgetattr(fd); tty.setcbreak(fd)
    out = sys.stdout
    out.write("\033[?1049h\033[?25l" + MOUSE_ON); out.flush(); t0 = time.time()
    try:
        loop(read_key, lambda rows: (out.write("\033[?2026h\033[H" + "\033[K\n".join(rows) + "\033[K\033[J\033[?2026l"), out.flush()),    # one synchronised write: no tearing
             lambda: (a.width or term_size()[0], a.height or term_size()[1]),
             lambda: build(a.history), stop=lambda: bool(a.exit_after) and time.time() - t0 > a.exit_after, heartbeat=beat,
             work=lambda st, ui: (mark_shown(st["session"]), autopilot(st, ui))[1], emit=lambda s: (out.write(s), out.flush()))
    except KeyboardInterrupt:
        pass
    finally:
        out.write(MOUSE_OFF + "\033[?25h\033[?1049l"); out.flush()
        try: os.remove(coach.ALIVE)
        except OSError: pass
        if os.name == "nt": _win_stop()
        else: termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
