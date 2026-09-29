"""watch.py - a readable, keyboard-driven panel for a second terminal pane. No animation.

One column per thread (a thread = one Claude Code session). THIS THREAD is pinned on the left; earlier threads sit
to its right, newest first. Every prompt is shown in full with the fix for each failed rule and any AFTER rewrite.

  <- / -> (h / l, Tab)   move between threads; the view pans horizontally to keep the focused one visible
  n / p                  select the next / previous prompt in the focused thread (marked with *)
  Enter                  open the selected prompt full width: your prompt, the rule hints, advice, the ENHANCED PROMPT (Esc closes)
  c                      copy the selected prompt's enhanced prompt to the clipboard, exactly as written
  e                      have Claude write an enhanced prompt for the selected one (sends that redacted prompt to your subscription)
  up / down (k / j)      scroll     PgUp / PgDn   a page      g / G   top / newest
  q or Ctrl+C            quit

  python watch.py            interactive
  python watch.py --once     print one plain frame and exit (also used when stdin is not a terminal)

Reads local history only, calls no LLM, redacts prompt text. The screen redraws only on a key or when new data arrives.
"""
import argparse, datetime as dt, json, os, re, shutil, sys, textwrap, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import advisor
import coach
import discover

MAX_THREADS, MIN_CW, MAX_CW = 40, 30, 48
POSIX_KEYS = {"[A": "up", "[B": "down", "[C": "right", "[D": "left", "[5~": "pgup", "[6~": "pgdn", "[H": "home", "[F": "end",
              "[1~": "home", "[4~": "end", "OA": "up", "OB": "down", "OC": "right", "OD": "left", "OH": "home", "OF": "end"}
WIN_KEYS = {"H": "up", "P": "down", "K": "left", "M": "right", "I": "pgup", "Q": "pgdn", "G": "home", "O": "end"}
ALIASES = {"h": "left", "l": "right", "\t": "right", "k": "up", "j": "down", "g": "home", "G": "end", "\x03": "q", "Q": "q",
           "n": "next", "]": "next", "p": "prev", "[": "prev", "c": "copy", "e": "enhance", "\r": "enter", "\n": "enter", "\x1b": "esc"}
IO = type("IO", (), {"copy": staticmethod(coach.copy_text), "enhance": staticmethod(coach.spawn_key)})  # swapped for fakes in tests


# ---------------------------------------------------------------- data
def load_full(path):
    """(unix_seconds, project, text, session_id) rows, oldest first. Malformed lines are skipped."""
    rows = []
    try:
        f = open(path, encoding="utf-8")
    except OSError:
        return rows
    with f:
        for l in f:
            try:
                r = json.loads(l)
                rows.append((float(r["timestamp"]) / 1000, r.get("project") or "", str(r["display"]).strip(), str(r.get("sessionId") or "")))
            except (ValueError, KeyError, TypeError):
                continue
    return sorted(rows)


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


def build(path):
    """{"threads": [...]}: the current thread first (always), then earlier threads that have flagged prompts, newest first."""
    rows = load_full(path); aft = rewrites()
    if not rows: return {"threads": [{"sid": "", "current": True, "label": "THIS THREAD", "sub": "no prompts yet", "entries": [], "scored": 0}]}
    cur_sid = rows[-1][3]; per = {}; meta = {}; prev = None
    for ts, proj, text, sid in rows:
        gap = None if prev is None else ts - prev; prev = ts
        m = meta.setdefault(sid, {"first": ts, "last": ts, "proj": proj, "scored": 0}); m["last"] = ts; m["proj"] = proj or m["proj"]
        if not coach.scorable(text) or text.startswith("/coach"): continue
        m["scored"] += 1
        fails = [n for n, fn in coach.RULES if not fn(text, gap)]
        key = coach.prompt_key((ts, proj, text))
        if not fails and key not in aft: continue    # nothing to say about this prompt
        rec = aft.get(key) or {}
        adv = rec.get("advice") or {}
        extra = advisor.lines(adv, 200) if adv else [("after", l) for l in coach._after_lines(rec["text"], 200)] if rec.get("text") else []
        if rec.get("discovery"): extra += discover.lines(rec["discovery"], 200)
        if rec.get("error") and not adv: extra = [("dim", "advice failed: " + str(rec["error"])[:120] + " (press e to retry)")]
        after = adv.get("after") or (re.sub(r"^AFTER:\s*", "", rec.get("text", "")).strip() if rec.get("text") else "")
        per.setdefault(sid, []).append({"ts": ts, "key": key, "score": 5 - len(fails), "text": coach.redact(text).replace("\n", " ")[:400],
                                        "full": coach.redact(text).replace("\n", " ")[:2000], "fixes": [f"{n}: {coach.FIX[n]}" for n in fails],
                                        "extra": extra, "advice": adv, "after": after, "error": None if adv else rec.get("error"),
                                        "disc": discover.lines(rec["discovery"], 200) if rec.get("discovery") else [], "off": coach.llm_off(proj)})
    def thread(sid, current):
        m = meta[sid]; d = lambda t: dt.datetime.fromtimestamp(t).strftime("%m-%d")
        span = d(m["first"]) if d(m["first"]) == d(m["last"]) else f"{d(m['first'])}>{d(m['last'])}"
        proj = os.path.basename(m["proj"].replace("\\", "/").rstrip("/")) or "-"
        n = len(per.get(sid, []))
        return {"sid": sid, "current": current, "label": "THIS THREAD" if current else f"{span}  {proj}"[:40],
                "sub": f"{n} flagged of {m['scored']}", "entries": per.get(sid, []), "scored": m["scored"]}
    others = sorted((s for s in per if s != cur_sid), key=lambda s: -meta[s]["last"])[:MAX_THREADS]
    return {"threads": [thread(cur_sid, True)] + [thread(s, False) for s in others]}


def signature(st):
    return tuple((t["sid"], len(t["entries"]), sum(len(e["extra"]) for e in t["entries"])) for t in st["threads"])


# ---------------------------------------------------------------- rendering
def column_layout(t, iw, marker=None, pending=None):
    """([(kind, text)], [start line of each entry]) for one thread, wrapped to iw. Nothing is truncated."""
    if not t["entries"]:
        return [("dim", "nothing flagged yet" if t["scored"] else "no prompts yet")], []
    out, starts, pending = [], [], pending or {}
    for n, e in enumerate(t["entries"]):
        starts.append(len(out))
        out.append(("head%d" % e["score"], ("* " if n == marker else "") + f"[{e['score']}/5] " + dt.datetime.fromtimestamp(e["ts"]).strftime("%m-%d %H:%M")))
        out += [("text", w) for w in textwrap.wrap('"' + e["text"] + '"', iw)]
        for f in e["fixes"]: out += [("dim", w) for w in textwrap.wrap("- " + f, iw, subsequent_indent="  ")]
        for kind, a in e["extra"]: out += [(kind, w) for w in textwrap.wrap(a, iw, subsequent_indent="      ") or [""]]
        if e["key"] in pending and not e["after"] and time.time() - pending[e["key"]] < 150: out.append(("dim", "(asking Claude... about 20s)"))
        out.append(("blank", ""))
    return out[:-1], starts


def column_lines(t, iw):
    return column_layout(t, iw)[0]


def new_ui():
    return {"focus": 0, "vs": 0, "off": {}, "follow": True, "lens": {}, "body_h": 10,
            "sel": {}, "detail": False, "dscroll": 0, "pending": {}, "msg": "", "reveal": None}


CODE = {"head5": "32", "head4": "32", "head3": "33", "head2": "31", "head1": "31", "head0": "31", "text": "0", "dim": "2", "after": "36", "blank": "0",
        "task": "1;35", "use": "32", "get": "34", "tip": "33", "flow": "2;37", "why": "2", "better": "1;36", "src": "2;36", "h": "1", "after2": "0"}


def render(st, ui, W, H, color=True):
    """The frame as a list of lines. Pure apart from writing scroll bookkeeping into ui."""
    def c(code, s): return f"\033[{code}m{s}\033[0m" if color and code != "0" else s
    W = max(W, 24); H = max(H, 8)
    if ui.get("detail") and cur_entry(ui, st)[2] is not None: return detail_frame(st, ui, W, H, color)
    th = st["threads"]; n = len(th)
    ui["focus"] = min(max(ui["focus"], 0), n - 1)
    cw = max(MIN_CW, min(MAX_CW, (W - 1) // 2))
    if W >= 2 * MIN_CW + 1:                      # pinned current thread + as many scrollable columns as fit
        n_vis = max(1, (W + 1) // (cw + 1) - 1); shown = [0]; m = n - 1
        if m:
            f = ui["focus"] - 1 if ui["focus"] >= 1 else None
            if f is not None: ui["vs"] = min(max(ui["vs"], f - n_vis + 1), f)
            ui["vs"] = min(max(ui["vs"], 0), max(m - n_vis, 0))
            shown += [1 + ui["vs"] + i for i in range(min(n_vis, m - ui["vs"]))]
    else:                                        # too narrow for two columns: show only the focused thread
        cw = W - 1; shown = [ui["focus"]]
    body_h = H - 1 - 1 - 2 - 1                   # spare row, title, 2 header rows, footer
    ui["body_h"] = body_h; cells = []
    for idx in shown:
        t = th[idx]; key = t["sid"] or "cur"
        sel = min(max(ui["sel"].get(key, len(t["entries"]) - 1), 0), max(len(t["entries"]) - 1, 0))
        lines, starts = column_layout(t, cw - 2, sel if idx == ui["focus"] and t["entries"] else None, ui["pending"])
        ui["lens"][key] = len(lines)
        bottom = max(len(lines) - body_h, 0)
        if t["current"] and ui["follow"]: off = bottom
        else: off = min(max(ui["off"].get(key, 0), 0), bottom)
        if ui.get("reveal") == key and starts:   # n / p moved the selection: scroll so the whole prompt is visible
            s0 = starts[sel]; e0 = starts[sel + 1] - 1 if sel + 1 < len(starts) else len(lines)
            if s0 < off or e0 > off + body_h: off = min(s0, bottom)
        ui["off"][key] = off
        pos = f"lines {off + 1}-{min(off + body_h, len(lines))} of {len(lines)}" if len(lines) > body_h else t["sub"]
        arrows = ("^" if off > 0 else " ") + ("v" if off < bottom else " ")
        head1 = ("> " if idx == ui["focus"] else "  ") + t["label"]
        cells.append(([head1[:cw], (t["sub"] if len(lines) <= body_h else f"{t['sub']} | {pos}")[:cw - 3] + " " + arrows],
                      [(k, x) for k, x in lines[off:off + body_h]], idx == ui["focus"]))
    ui["reveal"] = None
    rows = [c("1", "coachline"[:W - 1]) + c("2", ("  suggestions by thread  " + dt.datetime.now().strftime("%H:%M:%S"))[:max(W - 10, 0)])]
    def join(parts): return c("2", "│").join(parts)
    rows.append(join([c("7;1" if foc else "1", (" " + h1).ljust(cw)[:cw]) for (h1, _), _b, foc in [(x[0], x[1], x[2]) for x in cells]]))
    rows.append(join([c("2", (" " + h2).ljust(cw)[:cw]) for (_, h2), _b, _f in cells]))
    for r in range(body_h):
        parts = []
        for _h, body, _f in cells:
            k, x = body[r] if r < len(body) else ("blank", "")
            parts.append(c(CODE.get(k, "0"), (" " + x).ljust(cw)[:cw]))
        rows.append(join(parts))
    where = f"thread {ui['focus'] + 1} of {n}"
    rows.append(c("1;33", ui["msg"][:W - 1]) if ui["msg"] else
                c("2", f"{where} | h/l move  n/p prompt  Enter open  c copy  e enhance  j/k scroll  q quit"[:W - 1]))
    return rows[:H - 1]


def cur_entry(ui, st):
    """(thread, index, entry) of the selected prompt in the focused thread; the newest one unless n / p chose another."""
    t = st["threads"][min(ui["focus"], len(st["threads"]) - 1)]; es = t["entries"]
    if not es: return t, None, None
    i = min(max(ui["sel"].get(t["sid"] or "cur", len(es) - 1), 0), len(es) - 1)
    return t, i, es[i]


def detail_frame(st, ui, W, H, color=True):
    """One prompt, full width, as plain text: what you wrote, what the rules say, the advice, the ENHANCED PROMPT to copy."""
    def c(code, s): return f"\033[{code}m{s}\033[0m" if color and code != "0" else s
    t, i, e = cur_entry(ui, st); iw = max(W - 4, 20)
    L = [("h", "YOUR PROMPT")] + [("text", w) for w in textwrap.wrap(e["full"], iw)] + [("blank", "")]
    if e["fixes"]: L += [("h", "WHAT THE RULES SAY")] + [("dim", w) for f in e["fixes"] for w in textwrap.wrap("- " + f, iw, subsequent_indent="  ")] + [("blank", "")]
    adv = [(k, x) for k, x in advisor.lines(e["advice"], iw) if k != "after"] if e["advice"] else []
    if adv: L += [("h", "ADVICE")] + adv + [("blank", "")]
    if e["disc"]: L += [(k, w) for k, x in e["disc"] for w in textwrap.wrap(x, iw, subsequent_indent="   ") or [""]] + [("blank", "")]
    L.append(("h", "ENHANCED PROMPT" + ("   (press c to copy it; placeholders like [ASK: ...] or <email> are yours to fill in)" if e["after"] else "")))
    if e["after"]:
        for ln in e["after"].splitlines(): L += [("after2", w) for w in (textwrap.wrap(ln, iw) or [""])]
    elif e["error"]: L.append(("dim", f"advice failed: {str(e['error'])[:100]}. Press e to try again."))
    elif e["key"] in ui["pending"] and time.time() - ui["pending"][e["key"]] < 150: L.append(("dim", "asking Claude... about 20s; this updates by itself"))
    elif e["off"]: L.append(("dim", "this project is in llm-off.txt, so it is never sent to Claude."))
    else: L.append(("dim", "none yet. Press e to have Claude write one for this prompt (sends this redacted prompt to your Claude subscription)."))
    body_h = H - 3
    ui["dscroll"] = min(max(ui["dscroll"], 0), max(len(L) - body_h, 0))
    rows = [c("1", "coachline") + c("2", f"  prompt {i + 1} of {len(t['entries'])} in {t['label'].strip()}   [{e['score']}/5] "
                                       + dt.datetime.fromtimestamp(e["ts"]).strftime("%m-%d %H:%M"))[:max(W - 10, 0)]]
    for k, x in L[ui["dscroll"]:ui["dscroll"] + body_h]: rows.append(c(CODE.get(k, "0"), ("  " + x)[:W - 1]))
    rows += [""] * (body_h - len(L[ui["dscroll"]:ui["dscroll"] + body_h]))
    rows.append(c("1;33", ui["msg"][:W - 1]) if ui["msg"] else c("2", "Enter/Esc back  c copy enhanced prompt  e enhance  n/p other prompt  j/k scroll  q quit"[:W - 1]))
    return rows[:H - 1]


# ---------------------------------------------------------------- input
def handle(ui, st, key, io=None):
    """Apply one key to ui. True = quit. `io` (copy, enhance) is swapped for fakes in tests."""
    io = io or IO
    key = ALIASES.get(key, key); ui["msg"] = ""
    n = len(st["threads"]); t, i, e = cur_entry(ui, st); sid = t["sid"] or "cur"
    if key == "q": return True
    if key in ("next", "prev") and e is not None:
        j = min(max(i + (1 if key == "next" else -1), 0), len(t["entries"]) - 1)
        ui["sel"][sid] = j; ui["reveal"] = sid; ui["dscroll"] = 0
        if t["current"]: ui["follow"] = j == len(t["entries"]) - 1
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
        elif e["after"]: ui["msg"] = "already enhanced: press c to copy it"
        elif e["off"]: ui["msg"] = "this project is in llm-off.txt: not sending it to Claude"
        elif time.time() - ui["pending"].get(e["key"], 0) < 150: ui["msg"] = "already asking Claude about this prompt..."
        else:
            io.enhance(e["key"]); ui["pending"][e["key"]] = time.time()
            ui["msg"] = "asking Claude in the background (about 20s); the panel updates by itself"
        return False
    page = max(ui["body_h"] - 1, 1)
    if ui["detail"]:
        if key in ("up", "down", "pgup", "pgdn", "home", "end"):
            ui["dscroll"] = max(0, ui["dscroll"] + {"up": -1, "down": 1, "pgup": -page, "pgdn": page, "home": -10 ** 6, "end": 10 ** 6}[key])
        return False
    cur_off = ui["off"].get(sid, 0); bottom = max(ui["lens"].get(sid, 0) - ui["body_h"], 0)
    if key == "left": ui["focus"] = max(ui["focus"] - 1, 0)
    elif key == "right": ui["focus"] = min(ui["focus"] + 1, n - 1)
    elif key in ("up", "down", "pgup", "pgdn", "home", "end"):
        new = {"up": cur_off - 1, "down": cur_off + 1, "pgup": cur_off - page, "pgdn": cur_off + page, "home": 0, "end": bottom}[key]
        ui["off"][sid] = min(max(new, 0), bottom)
        if t["current"]: ui["follow"] = ui["off"][sid] >= bottom  # scrolling up stops auto-follow; reaching the newest resumes it
    return False


def read_key(timeout):
    """One key name ('left', 'q', 'j', ...) or None on timeout. Stdlib only: msvcrt on Windows, termios elsewhere."""
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


def loop(next_key, write, size, load_state, clock=time.time, reload_every=2.0, stop=lambda: False, heartbeat=lambda: None, io=None):
    """Draw only when something changed: a key, a new size, or new data. next_key(timeout) -> key|None."""
    ui = new_ui(); st = load_state(); last_load = clock(); last_size = None; dirty = True
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
        print("\n".join(render(build(a.history), new_ui(), a.width or 120, a.height or 40, color=False))); return
    if os.name == "nt": os.system("")  # switches the Windows console to ANSI mode
    else:
        import termios, tty
        fd = sys.stdin.fileno(); old = termios.tcgetattr(fd); tty.setcbreak(fd)
    sys.stdout.write("\033[?1049h\033[?25l"); t0 = time.time()
    try:
        loop(read_key, lambda rows: (sys.stdout.write("\033[H" + "\033[K\n".join(rows) + "\033[K\033[J"), sys.stdout.flush()),
             lambda: (a.width or shutil.get_terminal_size((100, 30)).columns, a.height or shutil.get_terminal_size((100, 30)).lines),
             lambda: build(a.history), stop=lambda: bool(a.exit_after) and time.time() - t0 > a.exit_after, heartbeat=beat)
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
