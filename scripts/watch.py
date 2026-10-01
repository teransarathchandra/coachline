"""watch.py - the coachline panel: THIS THREAD only, one column, analysed by Claude. No animation.

Your prompts are white. What can be improved is blue. At the top, "from your history": things Claude found by reading your
past chats (requests you repeat, mistakes you keep making) that also show up in this thread. Under each prompt: Claude's
improvements and an enhanced prompt you can copy.

  n / p        select the next / previous prompt (marked with *)
  Enter        open the selected prompt full width as plain text (Esc closes)
  c            copy the selected prompt's enhanced prompt to the clipboard, exactly as written
  e            have Claude analyse the selected prompt now
  s            install the skill Claude drafted for a request you keep repeating (never overwrites)
  j / k        scroll     PgUp / PgDn   a page      g / G   top / newest
  q or Ctrl+C  quit

  python watch.py            interactive
  python watch.py --once     print one plain frame and exit (also used when stdin is not a terminal)

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
ALIASES = {"k": "up", "j": "down", "g": "home", "G": "end", "\x03": "q", "Q": "q", "n": "next", "]": "next", "p": "prev", "[": "prev",
           "c": "copy", "e": "enhance", "s": "skill", "\r": "enter", "\n": "enter", "\x1b": "esc"}
IO = type("IO", (), {"copy": staticmethod(coach.copy_text), "enhance": staticmethod(coach.spawn_key),
                     "review": staticmethod(coach.spawn_review), "install": staticmethod(review.install_skill)})  # swapped for fakes in tests
# colours: your words white, what can be improved blue (bright blue reads on dark and light terminals)
CODE = {"title": "1", "time": "90", "prompt": "1;97", "head": "1;94", "blue": "94", "bluedim": "2;94", "rule": "2", "blank": "0",
        "task": "1;94", "use": "94", "get": "94", "tip": "94", "flow": "2;94", "better": "1;94", "src": "2;94", "dim": "2;94", "enh": "94"}
PENDING_SECONDS = 150


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
        text = f"You have asked for \"{slug}\" {past}x in past chats and {here}x in this thread -> " + (
            f"you already have /{slug}: use it" if installed else
            f"make it a skill, /{slug}" + (" (a draft is ready: press s to install it)" if drafted else " (draft it with /coach review)"))
        out.append({"kind": "request", "text": text, "slug": slug if drafted and not installed else None})
    for m in L.get("mistakes", []):
        here = _matches(here_txt, m.get("keywords", []))
        if not here: continue
        past = max(_matches(all_txt, m.get("keywords", [])) - here, 0)
        out.append({"kind": "mistake", "text": f"Recurring gap ({past}x before, {here}x here), {m['name']}: {m.get('fix', '')}", "slug": None})
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


def status_text(st):
    if not st["ai"]: return "Claude analysis is OFF. Turn it on: " + coach.py_cmd("setup.py", "--panel-ai", "on")
    if st["review_running"]: return "Claude is analysing your past chats right now..."
    L = st["learned"]
    if L.get("generated"): return f"Claude analysed {L.get('prompts', 'your')} prompts from your past chats on {L['generated']}"
    return "Claude will analyse your past chats in the background"


# ---------------------------------------------------------------- rendering
def _wrap(s, w, indent=""):
    return textwrap.wrap(s, w, subsequent_indent=indent) or [""]


def cur_entry(ui, st):
    """(index, entry) of the selected prompt: the newest unless n / p chose another. (None, None) when there are none."""
    es = st["entries"]
    if not es: return None, None
    i = min(max(ui["sel"] if ui["sel"] is not None else len(es) - 1, 0), len(es) - 1)
    return i, es[i]


def improvement_lines(e, iw, pending, ai):
    """[(kind, text)] for the blue part under a prompt."""
    out = []
    if e["advice"]:
        out.append(("head", "can be improved:"))
        out += [(k, "  " + x) for k, x in advisor.lines(e["advice"], iw - 2) if k != "after"]
        out += [(k, "  " + w) for k, x in e["disc"] for w in _wrap(x, iw - 2, "   ")]
    elif e["error"]: out.append(("bluedim", f"Claude's analysis failed ({str(e['error'])[:80]}). Press e to try again."))
    elif e["key"] in pending and time.time() - pending[e["key"]] < PENDING_SECONDS: out.append(("bluedim", "Claude is analysing this prompt... (about 20s)"))
    elif e["off"]: out.append(("bluedim", "this project is in llm-off.txt: never sent to Claude"))
    elif e["fails"]:
        out.append(("head", "can be improved:"))
        out += [("blue", "  " + w) for f in e["fixes"] for w in _wrap("- " + f, iw - 2, "  ")]
        out.append(("bluedim", "  (Claude's analysis is queued)" if ai and e["advisable"] else "  (press e for Claude's analysis and an enhanced prompt)"))
    return out


def body_layout(st, ui, iw, sel):
    """([(kind, text)], [start line of each entry]) for all of this thread's prompts."""
    if not st["entries"]: return [("bluedim", "no prompts in this thread yet")], []
    out, starts = [], []
    for n, e in enumerate(st["entries"]):
        starts.append(len(out))
        out.append(("time", ("* " if n == sel else "") + dt.datetime.fromtimestamp(e["ts"]).strftime("%H:%M")))
        out += [("prompt", w) for w in _wrap(e["text"], iw)]
        out += improvement_lines(e, iw, ui["pending"], st["ai"])
        if e["advice"] and e["after"]:
            out.append(("head", "enhanced prompt (press c to copy):"))
            for ln in e["after"].splitlines(): out += [("enh", "  " + w) for w in _wrap(ln, iw - 2)]
        out.append(("blank", ""))
    return out[:-1], starts


def new_ui():
    return {"sel": None, "off": 0, "follow": True, "lens": 0, "body_h": 10, "detail": False, "dscroll": 0, "pending": {}, "tried": set(),
            "review_after": 0.0, "msg": "", "reveal": False}


def render(st, ui, W, H, color=True):
    """The frame as a list of lines. Pure apart from scroll bookkeeping written into ui."""
    def c(code, s): return f"\033[{code}m{s}\033[0m" if color and code != "0" else s
    W = max(W, 30); H = max(H, 10)
    i, e = cur_entry(ui, st)
    if ui["detail"] and e is not None: return detail_frame(st, ui, i, e, W, H, color)
    iw = W - 3
    pinned = [("title", "coachline  this thread  " + dt.datetime.now().strftime("%H:%M:%S")), ("bluedim" if st["ai"] else "head", status_text(st))]
    ins = [(("blue", w) if True else None) for x in st["insights"] for w in _wrap("- " + x["text"], iw, "  ")]
    cap = max(3, H // 3)
    if len(ins) > cap: ins = ins[:cap - 1] + [("bluedim", "  ...")]
    pinned.append(("head", "FROM YOUR PAST CHATS"))
    pinned += ins or [("bluedim", "  (nothing you repeated in past chats shows up in this thread yet)")]
    pinned.append(("rule", "-" * (W - 2)))
    pinned = [(k, w) for k, t in pinned for w in (_wrap(t, W - 2) if k in ("title", "bluedim", "head") else [t])]
    body_h = max(H - 1 - len(pinned) - 1, 3)
    sel = i if e is not None else None
    lines, starts = body_layout(st, ui, iw, sel)
    ui["body_h"] = body_h; ui["lens"] = len(lines)
    bottom = max(len(lines) - body_h, 0)
    off = bottom if ui["follow"] else min(max(ui["off"], 0), bottom)
    if ui["reveal"] and starts:                       # n / p moved the selection: scroll so the whole prompt is visible
        s0 = starts[i]; e0 = starts[i + 1] - 1 if i + 1 < len(starts) else len(lines)
        if s0 < off or e0 > off + body_h: off = min(s0, bottom)
    ui["off"] = off; ui["reveal"] = False
    rows = [c(CODE[k], (" " + t)[:W - 1]) for k, t in pinned]
    shown = lines[off:off + body_h]
    rows += [c(CODE.get(k, "0"), (" " + t)[:W - 1]) for k, t in shown] + [""] * (body_h - len(shown))
    rows.append(c("1;33", ui["msg"][:W - 1]) if ui["msg"] else
                c("2", "n/p prompt  Enter open  c copy  e analyse  s skill  j/k scroll  q quit"[:W - 1]))
    return rows[:H - 1]


def detail_frame(st, ui, i, e, W, H, color=True):
    """One prompt, full width, as plain text: what you wrote, what can be improved, the ENHANCED PROMPT to copy."""
    def c(code, s): return f"\033[{code}m{s}\033[0m" if color and code != "0" else s
    iw = max(W - 4, 20)
    L = [("head", "YOUR PROMPT")] + [("prompt", w) for w in _wrap(e["text"], iw)] + [("blank", "")]
    imp = improvement_lines(e, iw, ui["pending"], st["ai"])
    if imp: L += [("head", "CAN BE IMPROVED")] + [(k, x) for k, x in imp if k != "head"] + [("blank", "")]
    L.append(("head", "ENHANCED PROMPT" + ("   (press c to copy it; [ASK: ...] and <email> placeholders are yours to fill in)" if e["after"] else "")))
    if e["after"]:
        for ln in e["after"].splitlines(): L += [("enh", w) for w in _wrap(ln, iw)]
    elif not e["advice"]:
        L.append(("bluedim", "none yet. Press e to have Claude write one for this prompt (sends this redacted prompt to your Claude subscription)."))
    body_h = H - 3
    ui["dscroll"] = min(max(ui["dscroll"], 0), max(len(L) - body_h, 0))
    rows = [c("1", "coachline") + c("2", f"  prompt {i + 1} of {len(st['entries'])}   " + dt.datetime.fromtimestamp(e["ts"]).strftime("%H:%M"))[:max(W - 10, 0)]]
    part = L[ui["dscroll"]:ui["dscroll"] + body_h]
    rows += [c(CODE.get(k, "0"), ("  " + x)[:W - 1]) for k, x in part] + [""] * (body_h - len(part))
    rows.append(c("1;33", ui["msg"][:W - 1]) if ui["msg"] else c("2", "Enter/Esc back  c copy enhanced prompt  e analyse  n/p other prompt  j/k scroll  q quit"[:W - 1]))
    return rows[:H - 1]


# ---------------------------------------------------------------- input
def handle(ui, st, key, io=None):
    """Apply one key to ui. True = quit. `io` (copy, enhance, review, install) is swapped for fakes in tests."""
    io = io or IO
    key = ALIASES.get(key, key); ui["msg"] = ""
    i, e = cur_entry(ui, st)
    if key == "q": return True
    if key in ("next", "prev") and e is not None:
        j = min(max(i + (1 if key == "next" else -1), 0), len(st["entries"]) - 1)
        ui["sel"] = j; ui["reveal"] = True; ui["dscroll"] = 0; ui["follow"] = j == len(st["entries"]) - 1
        return False
    if key == "enter":
        if e is not None: ui["detail"] = not ui["detail"]; ui["dscroll"] = 0
        return False
    if key == "esc": ui["detail"] = False; return False
    if key == "copy":
        if e is None: ui["msg"] = "no prompt selected"
        elif not e["after"]: ui["msg"] = "no enhanced prompt yet: press e to have Claude write one for this prompt"
        else:
            m = io.copy(e["after"])
            ui["msg"] = f"copied the enhanced prompt ({len(e['after'])} characters) via {m}" if m else "no clipboard available here: press Enter and select the text"
        return False
    if key == "enhance":
        if e is None: ui["msg"] = "no prompt selected"
        elif e["after"]: ui["msg"] = "already analysed: press c to copy the enhanced prompt"
        elif e["off"]: ui["msg"] = "this project is in llm-off.txt: not sending it to Claude"
        elif time.time() - ui["pending"].get(e["key"], 0) < PENDING_SECONDS: ui["msg"] = "already asking Claude about this prompt..."
        else:
            io.enhance(e["key"]); ui["pending"][e["key"]] = time.time()
            ui["msg"] = "asking Claude in the background (about 20s); the panel updates by itself"
        return False
    if key == "skill":
        slugs = [x["slug"] for x in st["insights"] if x.get("slug")]
        ui["msg"] = io.install(slugs[0])[1] if slugs else "no drafted skill to install yet (it appears after Claude analyses your past chats)"
        return False
    page = max(ui["body_h"] - 1, 1)
    delta = {"up": -1, "down": 1, "pgup": -page, "pgdn": page, "home": -10 ** 6, "end": 10 ** 6}.get(key)
    if delta is None: return False
    if ui["detail"]: ui["dscroll"] = max(0, ui["dscroll"] + delta)
    else:
        bottom = max(ui["lens"] - ui["body_h"], 0)
        ui["off"] = min(max(ui["off"] + delta, 0), bottom); ui["follow"] = ui["off"] >= bottom  # scrolling up stops auto-follow; the newest resumes it
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
    a = ap.parse_args(argv)
    if a.once or not (sys.stdin.isatty() and sys.stdout.isatty()):
        if not a.once: print("(not a terminal: printing one frame; run watch.py in a real terminal pane for the interactive view)")
        print("\n".join(render(build(a.history), new_ui(), a.width or 100, a.height or 40, color=False))); return
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
