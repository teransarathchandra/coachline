"""watch.py - a live terminal panel for a second pane.

  THIS THREAD      every flagged prompt of the current Claude Code session, kept on screen (newest at the bottom)
  EARLIER THREADS  flagged prompts from your other sessions, scrolling upward one line at a time

  python watch.py                run it (Ctrl+C quits); --speed 0.7 is seconds per scrolled line
  python watch.py --frames 5     print 5 plain frames and exit (demo / tests)

Suggestions are the local rule fixes, plus any AFTER rewrites the statusline's auto-rewrite already produced.
Nothing here calls an LLM. A "thread" is a sessionId from history.jsonl. Prompt text is redacted before display.
"""
import argparse, datetime as dt, json, os, shutil, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach

MAX_EARLIER = 80


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
                try: d = json.loads(l); out[d["key"]] = d["text"]
                except (ValueError, KeyError, TypeError): continue
    except OSError:
        pass
    return out


def build(path):
    """State for render(): current session id, its entries, earlier entries (newest first), counts."""
    rows = load_full(path); aft = rewrites()
    if not rows: return {"cur": "", "current": [], "earlier": [], "scored": 0}
    cur_sid = rows[-1][3]; per = {}; scored = 0; prev = None
    for ts, proj, text, sid in rows:
        gap = None if prev is None else ts - prev; prev = ts
        if not coach.scorable(text) or text.startswith("/coach"): continue
        if sid == cur_sid: scored += 1
        fails = [n for n, fn in coach.RULES if not fn(text, gap)]
        if not fails: continue
        e = {"ts": ts, "sid": sid, "score": 5 - len(fails), "text": coach.redact(text).replace("\n", " ")[:70],
             "fixes": [f"{n}: {coach.FIX[n]}" for n in fails[:3]], "after": []}
        if coach.prompt_key((ts, proj, text)) in aft: e["after"] = coach._after_lines(aft[coach.prompt_key((ts, proj, text))], 90)[:4]
        per.setdefault(sid, []).append(e)
    earlier = sorted((e for sid, es in per.items() if sid != cur_sid for e in es), key=lambda e: -e["ts"])[:MAX_EARLIER]
    return {"cur": cur_sid, "current": per.get(cur_sid, []), "earlier": earlier, "scored": scored}


def entry_lines(e):
    """[(kind, text)] for one entry; kind is header/fix/after/blank."""
    d = dt.datetime.fromtimestamp(e["ts"]).strftime("%m-%d %H:%M")
    return ([("header", f"{e['score']}/5  {d}  \"{e['text']}\"")] + [("fix", "    - " + f) for f in e["fixes"]]
            + [("after", "    " + a) for a in e["after"]] + [("blank", "")])


def _clip(s, w): return s if len(s) <= w else s[:max(w - 1, 0)] + "…"


def render(st, W, H, tick, color=True):
    """The frame as a list of lines (no trailing newline). Pure: same input, same output."""
    def c(code, s): return f"\033[{code}m{s}\033[0m" if color else s
    W = max(W, 30); H = max(H, 10)
    cur = [ln for e in st["current"] for ln in entry_lines(e)]
    while cur and cur[-1][0] == "blank": cur.pop()
    L = [ln for e in st["earlier"] for ln in entry_lines(e)]
    avail = H - 1 - 4  # title, two panel titles, footer; one spare row so the last line never scrolls the screen
    a_h = min(max(len(cur), 2), max(avail // 2, 3)); b_h = max(avail - a_h, 0)
    def seg(*parts):  # coloured pieces of one line, clipped as a whole so narrow panes never wrap
        left, res = W - 1, ""
        for code, text in parts:
            text = _clip(text, left); left -= len(text); res += c(code, text)
        return res
    out = [seg(("1", "coachline"), ("2", f"  live suggestions  {dt.datetime.now().strftime('%H:%M:%S')}"))]
    out.append(seg(("36", f"THIS THREAD  {len(st['current'])} flagged of {st['scored']} prompts"), ("2", "  (stays on screen)")))
    if not cur:
        body = [("fix", "  nothing flagged in this thread yet" if st["scored"] else "  no prompts in this thread yet")]
    else:
        body = cur if len(cur) <= a_h else [("fix", f"  ... {len(cur) - a_h + 1} earlier lines")] + cur[-(a_h - 1):]
    col = {"header": None, "fix": "2", "after": "36", "blank": "2"}
    for kind, text in body[-a_h:]:
        if kind == "header":
            sc = int(text[0]); code = "32" if sc >= 4 else "33" if sc == 3 else "31"
            out.append(c(code, _clip(text, W - 1)))
        else: out.append(c(col[kind], _clip(text, W - 1)))
    out += [""] * (a_h - len(body[-a_h:]))
    out.append(seg(("35", f"EARLIER THREADS  {len(st['earlier'])} suggestions"), ("2", "  (scrolling up)")))
    if not L:
        out.append(c("2", "  no flagged prompts in earlier threads")); out += [""] * (b_h - 1)
    else:
        L = L + [("blank", "")] * max(0, b_h + 2 - len(L))  # short lists still scroll
        for r in range(b_h):
            kind, text = L[(tick + r) % len(L)]
            shade = 238 + round(14 * r / max(b_h - 1, 1))  # dark at the top (leaving), lighter where entries arrive
            out.append(f"\033[38;5;{shade}m{_clip(text, W - 1)}\033[0m" if color else _clip(text, W - 1))
    out.append(seg(("2", "Ctrl+C to quit")))
    return out[:H - 1]


def main(argv):
    ap = argparse.ArgumentParser(); ap.add_argument("--history", default=coach.HIST)
    ap.add_argument("--speed", type=float, default=0.7); ap.add_argument("--frames", type=int, default=0)
    ap.add_argument("--width", type=int); ap.add_argument("--height", type=int)
    ap.add_argument("--ticks", type=int, default=0, help="live mode: exit after N redraws (tests)"); a = ap.parse_args(argv)
    if a.frames:  # plain, deterministic output: no ANSI, no sleeping
        st = build(a.history); W, H = a.width or 100, a.height or 30
        for t in range(a.frames):
            print(f"=== frame {t} ===\n" + "\n".join(render(st, W, H, t, color=False)))
        return
    if os.name == "nt": os.system("")  # switches the Windows console to ANSI mode
    sys.stdout.write("\033[?1049h\033[?25l"); tick = 0; st = None; nxt = 0
    try:
        while True:
            if time.time() >= nxt: st = build(a.history); nxt = time.time() + 2
            W, H = shutil.get_terminal_size((100, 30))
            sys.stdout.write("\033[H" + "\033[K\n".join(render(st, a.width or W, a.height or H, tick)) + "\033[K\033[J"); sys.stdout.flush()
            tick += 1
            if a.ticks and tick >= a.ticks: break
            time.sleep(a.speed)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h\033[?1049l"); sys.stdout.flush()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
