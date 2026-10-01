"""Claude Code statusLine: plain-English coaching for your last and next prompt, plus how to open the panel. Never raises."""
import json, os, sys, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def read_stdin(timeout=0.5):
    """Claude Code pipes session JSON in. Never block on a terminal or a pipe that does not close."""
    if sys.stdin is None or sys.stdin.isatty(): return {}
    box = []
    t = threading.Thread(target=lambda: box.append(sys.stdin.read()), daemon=True)
    t.start(); t.join(timeout)
    try: return json.loads(box[0]) if box else {}
    except ValueError: return {}


try:
    sys.stdout.reconfigure(encoding="utf-8")
    import coach, nudge
    sid = str(read_stdin().get("session_id") or "")
    rows = coach.load(coach.HIST); i, fails = coach.last_eval(rows)
    last = coach.last_session(coach.HIST)
    fresh = bool(sid and last and sid != last)          # this session has not sent a prompt yet: never show the previous session's results
    for code, text in nudge.lines(rows, i, fails, fresh): print(f"\033[{code}m{text}\033[0m")
    if i is not None and not fresh:
        habit = coach.habit_note(rows[i][2])             # learned from your own history by review.py; local, no LLM call
        if habit: print(f"\033[35m{habit}\033[0m")
        for l in coach.auto_after(rows, i, fails): print(f"\033[36m{l}\033[0m")   # opt-in advisor block, from a background job
    hint = nudge.panel_hint()
    if hint: print(f"\033[{hint[0]}m{hint[1]}\033[0m")
except Exception:
    pass
