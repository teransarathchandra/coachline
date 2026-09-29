"""coachline - score your last Claude Code prompt against 5 rules, spot repeated requests.

Stdlib only. Reads <config>/history.jsonl (read-only). Writes only under <config>/coach/.
  python coach.py              replay report over your whole history
  python coach.py --coach      before/after for your last prompt (Haiku rewrite via `claude -p`)
  python coach.py --doctor     check that everything this tool depends on works
"""
import argparse, collections, datetime as dt, json, os, re, shutil, subprocess, sys, tempfile

CONFIG = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
HIST = os.path.join(CONFIG, "history.jsonl")
STATE = os.path.join(CONFIG, "coach")  # survives plugin updates; the plugin dir does not
OFF = os.path.join(STATE, "llm-off.txt")        # one path substring per line: never sent to an LLM
USER_CFG = os.path.join(STATE, "config.json")    # {"categories": {"name": "regex"}}
PASTE = re.compile(r"\[Pasted text #\d+ \+(\d+) lines\]")
BARE = re.compile(r"^(continue|yes|ok|confirm|go ahead|keep going|resume|clear)\W*$", re.I)

_SECRETS = [
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>"),
    (r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<guid>"),
    (r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}\b", "<jwt>"),
    (r"\b(sk|pk|ghp|gho|ghs|xox[bap]|AKIA)[-_A-Za-z0-9]{16,}", "<key>"),
    (r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{16,}", "<token>"),
    (r"(?i)\b(password|passwd|pwd|secret|accountkey|sharedaccesskey|api[_-]?key|token)\s*[=:]\s*\S+", "<secret>"),
]

def redact(t):
    for pat, sub in _SECRETS:
        t = re.sub(pat, sub, t)
    return t

def body(t):  # strip leading /command and paste markers for text analysis
    t = re.sub(r"^/\S+\s*", "", t.strip())
    return PASTE.sub(" ", t).strip()

# --- the five rules (True = passes). Heuristics, English only. -------------
def r1_done_when(t, _p=None):
    b = body(t)
    return len(b.split()) <= 25 or bool(re.search(r"\b(done|should|expect\w*|until|passes|verify|so that)\b", b, re.I))
def r2_dont_touch(t, _p=None):
    b = body(t)
    risky = re.search(r"\b(merge|migration|deploy\w*|force|revert|release)\b", b, re.I)
    return not risky or bool(re.search(r"\b(don'?t|do not|only|without|never)\b", b, re.I))
def r3_evidence(t, _p=None):
    return all(int(n) <= 150 for n in PASTE.findall(t))
def r4_qualifiers(t, _p=None):
    return not re.search(r"\b(carefully|properly|best|clean)\b", body(t), re.I)
REJECT = re.compile(r"\b(still|not like this|previous way|not working|doesn'?t work|isn'?t working|not what i|wrong|undo)\b|^(dont|don'?t|no\b)", re.I)
def r5_rejection(t, prev):
    if not REJECT.search(" ".join(body(t).split()[:14])):
        return True
    return not (prev is not None and prev < 900 and not re.search(r"\b(because|rule|instead)\b", body(t), re.I))
RULES = [("done-when", r1_done_when), ("dont-touch", r2_dont_touch), ("evidence", r3_evidence),
         ("no-vague", r4_qualifiers), ("rejection-loop", r5_rejection)]
FIX = {"done-when": "say what proves it is finished (a command, a result, a state)",
       "dont-touch": "list what must NOT change (branches, files, data)",
       "evidence": "paste only the relevant lines, not the whole log",
       "no-vague": "replace 'carefully/best/clean' with a checkable rule or a reference",
       "rejection-loop": "say WHICH rule the last output broke, so it becomes a constraint"}

CATS = {
    "commit/PR/ticket text": r"commit message|pr title|pr description|ticket.*comment|comment.*ticket|\bpr\b$",
    "install/setup": r"\b(install|set ?up)\b",
}

def categories():
    try:
        extra = json.load(open(USER_CFG, encoding="utf-8")).get("categories", {})
    except (OSError, ValueError, AttributeError):
        extra = {}
    return {**CATS, **{k: v for k, v in extra.items() if isinstance(v, str)}}

def load(path):
    """Rows of (unix_seconds, project, text). Skips malformed lines; history.jsonl is not a public format."""
    rows = []
    try:
        f = open(path, encoding="utf-8")
    except OSError:
        return rows
    with f:
        for l in f:
            try:
                r = json.loads(l)
                rows.append((float(r["timestamp"]) / 1000, r.get("project") or "", str(r["display"]).strip()))
            except (ValueError, KeyError, TypeError):
                continue
    return sorted(rows)

def scorable(t):
    return not (BARE.match(t) or re.match(r"^/\S+$", t) or len(body(t).split()) < 3)

def analyse(rows):
    fails = collections.Counter(); scored = 0; bare = 0
    weeks = collections.defaultdict(collections.Counter)
    prev_ts = None; hits = collections.defaultdict(list); cats = categories()
    for ts, proj, t in rows:
        gap = None if prev_ts is None else ts - prev_ts
        prev_ts = ts
        wk = dt.date.fromtimestamp(ts).strftime("%G-W%V")
        if BARE.match(t): bare += 1; weeks[wk]["bare approvals"] += 1; continue
        if not scorable(t): continue
        scored += 1
        for name, fn in RULES:
            if not fn(t, gap):
                fails[name] += 1
                if name == "rejection-loop": weeks[wk]["rejection loops"] += 1
                if name == "done-when": weeks[wk]["no done-when"] += 1
        weeks[wk]["prompts"] += 1
        for cat, pat in cats.items():
            if re.search(pat, body(t), re.I): hits[cat].append((ts, redact(t)[:90]))
    return scored, fails, bare, weeks, hits

def clusters(hits, days=14, need=3):
    """Densest 14-day window per category: (total, count_in_window, start_date, last_example_in_window)."""
    out = {}
    for cat, xs in hits.items():
        xs.sort()
        j = 0; best = (0, 0, 0)  # (count, first index, last index) of the densest window
        for i in range(len(xs)):  # two pointers: O(n), the old scan was O(n^2) and took 13s on 30k prompts
            while xs[i][0] - xs[j][0] > days * 86400: j += 1
            if i - j + 1 > best[0]: best = (i - j + 1, j, i)
        if best[0] >= need:
            out[cat] = (len(xs), best[0], dt.date.fromtimestamp(xs[best[1]][0]).isoformat(), xs[best[2]][1])
    return out

def draft(cat, n, example):
    slug = re.sub(r"\W+", "-", cat.lower()).strip("-")
    p = os.path.join(STATE, "drafts", slug, "SKILL.md"); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(f"---\nname: {slug}\ndescription: DRAFT - you asked '{cat}' {n} times. Edit before use.\n---\n"
                f"Example of your past request: {example}\nWrite the exact steps and output format here.\n")
    return p

def report(path):
    rows = load(path); scored, fails, bare, weeks, hits = analyse(rows)
    print(f"{len(rows)} history entries, {scored} scored prompts, {bare} bare approvals\n")
    print("RULE HIT RATES (fail %; >40% = noise, drop the rule)")
    for name, _ in RULES:
        pct = 100 * fails[name] / max(scored, 1)
        print(f"  {name:15} {fails[name]:4} fails  {pct:5.1f}%  {'<-- NOISE' if pct > 40 else ''}")
    print("\nWEEKLY COUNTERS")
    for wk in sorted(weeks):
        c = weeks[wk]
        print(f"  {wk}  prompts={c['prompts']:3}  rejection-loops={c['rejection loops']}  no-done-when={c['no done-when']}  bare-approvals={c['bare approvals']}")
    print("\nREPEATS (3+ in any 14 days)")
    cl = clusters(hits)
    for cat, (total, win, start, ex) in cl.items():
        print(f"  {cat}: {total} total, densest {win} in 14 days from {start} -> draft {draft(cat, total, ex)}")
    if not cl: print("  none")

def last_eval(rows):
    """(index, failed rule names) for the newest scorable prompt that is not a /coach call."""
    for i in range(len(rows) - 1, -1, -1):
        t = rows[i][2]
        if t.startswith("/coach") or not scorable(t):
            continue
        gap = rows[i][0] - rows[i - 1][0] if i else None
        return i, [n for n, fn in RULES if not fn(t, gap)]
    return None, []

def verdict(text, fails):
    """'n/5' when a rule fired or the prompt was long enough to test; else 'short'.
    A green 5/5 on a 6-word prompt is false praise: done-when only applies past 25 words."""
    return f"{5 - len(fails)}/5" if fails or len(body(text).split()) > 25 else "short"

def repeat_note(rows, i):
    """If prompt i is a category you asked 3+ times in the 14 days up to it, return a one-line note."""
    ts = rows[i][0]
    recent = [r for r in rows[max(0, i - 5000):i + 1] if ts - r[0] <= 14 * 86400]
    for cat, xs in analyse(recent)[4].items():
        if len(xs) >= 3 and any(x[0] == ts for x in xs):
            return f"'{cat}' asked {len(xs)}x in the last 14 days"
    return None

def llm_off(proj):
    try:
        with open(OFF, encoding="utf-8") as f:
            return any(l.strip() and l.strip().lower() in proj.lower() for l in f)
    except OSError:
        return False

def rewrite(text, fails):
    if not shutil.which("claude"):
        return "(rewrite skipped: `claude` CLI not on PATH)"
    ask = ("Rewrite this coding-agent prompt so it satisfies the failed checks, keeping the user's intent and facts. "
           "Failed checks: " + ", ".join(fails or ["none"]) + ". Use a Goal / Don't touch / Done-when layout only if it helps. "
           "Never invent facts: put [ASK: ...] where the user must supply one. "
           "Output exactly: AFTER: <prompt> then WHY: <2 short lines>.\n\nPROMPT:\n" + text[:4000])  # keep the argv under Windows' 32k limit
    try:
        r = subprocess.run(["claude", "-p", "--model", "haiku", "--no-session-persistence", "--disable-slash-commands",
                            "--tools", "", "--setting-sources", "", ask],
                           capture_output=True, text=True, encoding="utf-8", timeout=90, cwd=tempfile.gettempdir())
    except subprocess.TimeoutExpired:
        return "(rewrite timed out after 90s)"
    return (r.stdout or r.stderr).strip()

def coach(path, llm=True):
    rows = load(path); i, fails = last_eval(rows)
    if i is None: print("No scorable prompt found. Run `--doctor` to check your history file."); return
    _ts, proj, t = rows[i]
    print(f"BEFORE ({verdict(t, fails)}): {redact(t)[:400]}\n")
    for f in fails: print(f"  x {f}: {FIX[f]}")
    if not fails: print("  no rule fired" + (" (short prompt: most rules do not apply)" if verdict(t, fails) == "short" else ""))
    n = repeat_note(rows, i)
    if n: print(f"\nREPEAT: {n}. Draft skills are in {os.path.join(STATE, 'drafts')} (review, then move into your skills folder yourself).")
    if not llm: return
    if llm_off(proj): print(f"\n(LLM rewrite skipped: project matches an entry in {OFF})"); return
    print("\n" + rewrite(redact(t), fails))

def script_of(cmd):
    """Path of the statusline.py a statusLine command runs, or None. Handles quoted paths with spaces."""
    import shlex
    try: parts = shlex.split(cmd)
    except ValueError: parts = cmd.split()
    return next((p for p in parts if p.lower().endswith("statusline.py")), None)

def doctor(path):
    ok = True
    def line(good, msg):
        nonlocal ok; ok &= good; print(("ok   " if good else "FAIL ") + msg)
    rows = load(path)
    line(os.path.isfile(path), f"history file: {path}")
    line(bool(rows), f"parsed {len(rows)} prompts (needs JSONL with 'display' and 'timestamp' fields)")
    line(sys.version_info >= (3, 9), f"python {sys.version.split()[0]} at {sys.executable}")
    print(("ok   " if shutil.which("claude") else "warn ") + "claude CLI on PATH (needed only for the /coach rewrite)")
    try:
        sl = json.load(open(os.path.join(CONFIG, "settings.json"), encoding="utf-8")).get("statusLine", {})
    except (OSError, ValueError):
        sl = {}
    cmd = sl.get("command", "")
    print(("ok   " if "statusline.py" in cmd else "warn ") + f"statusLine: {cmd or 'not set (run scripts/setup.py)'}")
    script = script_of(cmd)
    if script: line(os.path.isfile(script), f"statusline script exists: {script} (run setup.py again if not)")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(); ap.add_argument("--history", default=HIST)
    ap.add_argument("--coach", action="store_true"); ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--doctor", action="store_true"); ap.add_argument("--show", action="store_true", help="list rejection-rule hits")
    a = ap.parse_args()
    if a.doctor: doctor(a.history)
    elif a.coach: coach(a.history, llm=not a.no_llm)
    else:
        report(a.history)
        if a.show:
            print("\nREJECTION FLAGS")
            prev = None
            for ts, _proj, t in load(a.history):
                gap = None if prev is None else ts - prev; prev = ts
                if scorable(t) and not r5_rejection(t, gap): print("  -", redact(t)[:110])
