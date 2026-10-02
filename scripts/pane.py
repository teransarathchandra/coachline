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
