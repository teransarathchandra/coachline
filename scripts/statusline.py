"""Claude Code statusLine: score of your last prompt + repeat nudge. Never raises."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")
    import coach
    rows = coach.load(coach.HIST); i, fails = coach.last_eval(rows)
    if i is not None:
        v = coach.verdict(rows[i][2], fails); n = 5 - len(fails)
        col = "2" if v == "short" else "32" if n >= 4 else "33" if n == 3 else "31"  # 2 = dim
        print(f"\033[{col}mcoach {v}\033[0m" + (" | " + ", ".join(fails) if fails else "") + "  (/coach for before/after)")
        note = coach.repeat_note(rows, i)
        if note: print(f"\033[36mrepeat:\033[0m {note}")
        habit = coach.habit_note(rows[i][2])  # learned from your own history by review.py; local, no LLM call
        if habit: print(f"\033[35m{habit}\033[0m")
except Exception:
    pass
