"""pane.py - the coachline panel for Claude Code's own pane (hooks/coachline.tsx): one tick, no drawing.

  python pane.py --json --session ID [--width N]   this thread's state as JSON; queues Claude's analysis when it is on
                                                   (--width 0: lines unwrapped, for a pane that wraps them itself)
  python pane.py --enhance KEY [--session ID]      ask Claude about one prompt now (the pane's Analyse button)
  python pane.py --install SLUG                    install a skill Claude drafted (the pane's Install button)
  python pane.py --mark dismissed|adopted ID       hide a web suggestion for good, or note that you use it (the pane's buttons)
  python pane.py --research KEY [--session ID]     search the web again for one analysed prompt (the pane's Look again button)

Each call is a fresh process, so what watch.py keeps in memory between frames (which prompts were sent, when the history review is
next due) is kept in ~/.claude/coach/pane-<session>.json. When a standalone panel (watch.py) is open, it does the background work.
"""
import argparse, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach, discover, review, watch

LOCK_SECONDS = 30   # a tick holding the lock longer than this died; the next one takes over


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
        coach.write_json(ui_path(session), {"pending": ui["pending"], "tried": sorted(ui["tried"]), "review_after": ui["review_after"]})
    except OSError:
        pass


def lock_path(session):
    return ui_path(session)[:-len(".json")] + ".lock"


def take_lock(session):
    """True when this tick may do the background work for `session`: no other pane.py for it is mid-tick. Two overlapping ticks would
    both read the saved state before either wrote it, and send the same prompt twice."""
    p = lock_path(session)
    for _ in range(2):
        try:
            os.makedirs(coach.STATE, exist_ok=True)
            os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)); return True
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(p) < LOCK_SECONDS: return False
                os.remove(p)
            except OSError: return False
        except OSError:
            return False
    return False


def standalone_shows(session):
    """A standalone panel (watch.py) is open on this session, so it does the background work. One on another session does not."""
    if not coach.panel_alive(): return False
    try:
        with open(os.path.join(coach.STATE, "watch.session"), encoding="utf-8") as f: shown = f.read().strip()
    except OSError:
        return True                                     # a panel too old to say which session it shows: leave the work to it
    return shown in ("", session)


UNWRAPPED = 10 ** 6                    # --width 0: one line per paragraph; the Claude Code pane wraps each to its own width


def tick(session, width=80, io=None, now=None):
    work = coach.auto_open_on()                         # auto-open off: the pane never shows, so nothing is sent and no notice used up
    st = watch.build(coach.HIST, session=session, notice=work)
    ui = load_ui(session)
    if work and not standalone_shows(session) and take_lock(session):
        try:
            ui = load_ui(session)                       # what the tick before ours saved
            watch.autopilot(st, ui, io=io, now=now)
            save_ui(session, ui)
        finally:
            try: os.remove(lock_path(session))
            except OSError: pass
    iw = UNWRAPPED if width <= 0 else max(20, min(width, watch.MAX_WIDTH) - 4)
    entries = []
    for i, e in enumerate(st["entries"]):
        state, glyph, _kind, words = watch.status(e, st, ui)
        entries.append({"key": e["key"], "stamp": watch.stamp(e["ts"]), "glyph": glyph, "state": state, "words": words,
                        "text": e["text"], "after": e["after"], "lines": [list(l) for l in watch.card_lines(st, ui, i, e, iw, acts=True)]})
    skill = next((x["slug"] for x in st["insights"] if x.get("slug")), None)
    return {"ai": st["ai"], "research": coach.research_on(), "researching": discover.researching(session), "auto_open": coach.auto_open_on(), "hints": coach.hints_on(), "session": st["session"], "entries": entries,
            "patterns": watch.pattern_texts(st), "skill": skill, "notice": st["notice"]}


def score(draft):
    """The hint under the prompt box for a draft being typed: local only, no lock, no state."""
    words = len(coach.body(draft).split())
    command = draft.lstrip()[:1] in ("!", "#") or coach.BUILTIN.match(draft.strip())   # a shell line, a memory note, a setting
    if not words or command or not coach.hints_on(): return {"meter": None, "hint": None, "words": 0, "hold": False}
    return {"meter": watch.meter(draft), "hint": coach.hint_for(draft, beginner=coach.level() == "beginner"), "words": words, "hold": coach.hold_on()}   # hold rides with the draft


def main(argv):
    ap = argparse.ArgumentParser(description="coachline panel state for the Claude Code pane")
    ap.add_argument("--json", action="store_true"); ap.add_argument("--session"); ap.add_argument("--width", type=int, default=80)
    ap.add_argument("--enhance", metavar="KEY"); ap.add_argument("--install", metavar="SLUG")
    ap.add_argument("--mark", nargs=2, metavar=("STATUS", "ID")); ap.add_argument("--research", metavar="KEY")
    ap.add_argument("--outcome", choices=("aborted", "next"), help="from the pane module: a turn you interrupted (the prompt on stdin), or "
                    "your next prompt ({prev, text} JSON on stdin); recorded locally, nothing is printed or sent")
    ap.add_argument("--score", action="store_true", help="the draft on stdin -> its meter and hint as JSON (nothing is saved or sent)")
    a = ap.parse_args(argv)
    if a.outcome:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        try:
            if a.outcome == "aborted": coach.record_outcome("aborted", raw)
            else:
                d = json.loads(raw)
                if isinstance(d, dict) and coach.is_correction(str(d.get("text", ""))): coach.record_outcome("corrected", str(d.get("prev", "")))
        except (ValueError, OSError): pass                    # evidence is a bonus: never fail the pane over it
        return 0
    if a.score:
        # bytes in, ASCII out: right whatever the console code page (cp1252 on Windows), and JSON.parse reads the escapes
        sys.stdout.write(json.dumps(score(sys.stdin.buffer.read().decode("utf-8", "replace")))); return 0
    if a.enhance:
        coach.spawn_key(a.enhance)
        if a.session:                                   # so the pane shows it as being analysed, and the autopilot does not send it again
            ui = load_ui(a.session); ui["pending"][a.enhance] = time.time(); ui["tried"].add(a.enhance); save_ui(a.session, ui)
        print("asking Claude in the background (about 20 seconds)"); return 0
    if a.install:
        ok, msg = review.install_skill(a.install); print(msg); return 0 if ok else 1
    if a.mark:
        import memory
        status, iid = a.mark
        if status not in memory.STATUSES: print("status must be dismissed or adopted", file=sys.stderr); return 2
        if not memory.mark(iid, status): print("could not save that choice", file=sys.stderr); return 1
        print("hidden: it will not be suggested again" if status == "dismissed" else "noted: it will not be suggested again"); return 0
    if a.research:
        why = discover.research_refusal(a.research)
        if why: print(why, file=sys.stderr); return 1
        coach.spawn_research(a.research)
        print("searching the web for this task in the background (up to ~4 minutes)"); return 0
    if a.json and a.session:
        sys.stdout.write(json.dumps(tick(a.session, a.width), ensure_ascii=False)); return 0
    ap.print_help(); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
