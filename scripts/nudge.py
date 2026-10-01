"""nudge.py - what the statusline says. Plain English, never stale, no LLM, nothing hardcoded about YOU:
the gap it points at and the trend it draws are computed from your own prompt history.

  - about the last prompt: only when it belongs to THIS session (a new session shows nothing stale)
  - about the next one: your most common gap over your last 20 tested prompts, with a phrase to add
  - a tiny trend of recent prompt quality
  - when the panel is not open: the exact command to open it (a short path that survives plugin updates)
"""
import os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach

WATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watch.py")
SHORT = {"done-when": "say what proves it is done", "dont-touch": "say what must not change",
         "evidence": "paste only the relevant lines", "no-vague": "swap 'carefully/best' for something checkable",
         "rejection-loop": "say which rule the last answer broke"}
ADD = {"done-when": 'finish with "Done when: <what proves it works>"', "dont-touch": 'add "Don\'t touch: <files, branches, data>"',
       "evidence": "paste only the 5 relevant lines, not the whole log", "no-vague": 'replace "carefully/best" with a check you can run',
       "rejection-loop": "when it misses, say which rule it broke"}
BARS = {0: "█", 1: "▅", 2: "▃", 3: "▂"}   # by number of gaps in a prompt: none = full block, 3+ = lowest


def tested(rows, n):
    """[(index, failed rules)], oldest first, for the last n prompts long enough to be judged (not 'continue', not one-liners).
    Scans from the end and stops at n, so a huge history costs the same as a small one."""
    out = []
    for i in range(len(rows) - 1, -1, -1):
        ts, _p, t = rows[i]
        if not coach.scorable(t) or t.startswith("/coach"): continue
        gap = ts - rows[i - 1][0] if i else None
        fails = [name for name, fn in coach.RULES if not fn(t, gap)]
        if coach.verdict(t, fails) != "short":
            out.append((i, fails))
            if len(out) == n: break
    return out[::-1]


def top_gap(t):
    """(rule, count, total) from tested(): the rule most of those prompts fail, if it is a real pattern (>= 30% of at least 6)."""
    if len(t) < 6: return None
    counts = {name: sum(name in f for _i, f in t) for name, _fn in coach.RULES}
    rule = max(counts, key=counts.get)
    return (rule, counts[rule], len(t)) if counts[rule] / len(t) >= 0.3 else None


def spark(t, n=10):
    t = t[-n:]
    return "".join(BARS[min(len(f), 3)] for _i, f in t) if len(t) >= 3 else ""


def py_name():
    """The shortest way to say 'this Python' in the user's shell: python, python3, or the full path."""
    exe = sys.executable
    for name in ("python", "python3"):
        w = shutil.which(name)
        try:
            if w and os.path.samefile(w, exe): return name
        except OSError: pass
    return f'"{exe}"' if " " in exe else exe


def ensure_shim():
    """A launcher at a path that never changes (~/.claude/coach/panel.py); it forwards to this version's watch.py."""
    p = os.path.join(coach.STATE, "panel.py")
    body = ("# coachline: opens the thread panel. Rewritten automatically after plugin updates; safe to delete.\n"
            f"import runpy, sys\nsys.argv[0] = {WATCH!r}\nrunpy.run_path({WATCH!r}, run_name=\"__main__\")\n")
    try:
        try:
            with open(p, encoding="utf-8") as f: same = f.read() == body
        except OSError: same = False
        if not same:
            os.makedirs(coach.STATE, exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as f: f.write(body)
    except OSError:
        pass
    return p


def panel_command():
    p = ensure_shim().replace("\\", "/")
    return f"{py_name()} " + (f'"{p}"' if " " in p else p)


def lines(rows, i, fails, fresh):
    """[(ansi colour code, text)] for the statusline, top to bottom. The last line is the panel hint when it applies."""
    out = []
    if i is not None and not fresh:
        if fails:
            tail = "   (panel: e = rewrite)" if coach.panel_alive() else ""
            out.append(("31" if len(fails) >= 3 else "33", "last prompt: could be sharper -> " + "; ".join(SHORT[f] for f in fails[:2]) + tail))
        elif coach.verdict(rows[i][2], fails) != "short":
            out.append(("32", "last prompt: passes all 5 checks ✓"))
    t = tested(rows, 20)
    gap, sp = top_gap(t), spark(t)
    if sp: out.append(("36", f"your last {len(sp)} prompts {sp}  (taller bar = fewer gaps)" + ("" if gap else "   no gap is repeating lately")))
    if gap: out.append(("36", f"next prompt: {ADD[gap[0]]}   (your most common gap: {gap[1]} of your last {gap[2]})"))
    if i is not None and not fresh:
        info = coach.repeat_info(rows, i)
        if info: out.append(("35", f"you have asked for \"{info[0]}\" {info[1]}x in 14 days -> turn it into a one-word skill: /coach review"))
    return out


def panel_hint():
    """The line to show at the very bottom, or None. Off when the panel is open or you switched it off."""
    if coach.panel_alive() or coach.setting("panel_hint", True) is False: return None
    return ("2", "panel not open -> paste this in a new terminal tab to open it: " + panel_command())
