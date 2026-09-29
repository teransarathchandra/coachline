"""coachline - score your last Claude Code prompt against 5 rules, spot repeated requests.

Stdlib only. Reads <config>/history.jsonl (read-only). Writes only under <config>/coach/.
  python coach.py              replay report over your whole history
  python coach.py --coach      before/after for your last prompt (Haiku rewrite via `claude -p`)
  python coach.py --doctor     check that everything this tool depends on works
"""
import argparse, collections, datetime as dt, json, os, re, shutil, subprocess, sys, tempfile, time

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

def ask_claude(prompt, model="haiku", timeout=180):
    """One-shot question to the user's own Claude subscription via `claude -p`. No API key, no tools,
    no settings, no session saved. The prompt goes over stdin (no argv length limit, not visible in `ps`).
    COACHLINE_CLAUDE overrides the command (used by the tests). Returns text; raises RuntimeError on failure."""
    import shlex
    cmd = shlex.split(os.environ.get("COACHLINE_CLAUDE") or "claude") or ["claude"]  # use forward slashes in COACHLINE_CLAUDE
    if not os.environ.get("COACHLINE_CLAUDE") and not shutil.which(cmd[0]):
        raise RuntimeError("`claude` CLI not on PATH")
    try:
        r = subprocess.run(cmd + ["-p", "--model", model, "--no-session-persistence", "--disable-slash-commands",
                                  "--tools", "", "--setting-sources", ""],
                           input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                           cwd=tempfile.gettempdir())
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude timed out after {timeout}s")
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError((r.stderr or r.stdout or "claude returned nothing").strip()[:300])
    return r.stdout.strip()

def _rewrite_ask(text, fails, timeout=180):
    ask = ("Rewrite this coding-agent prompt so it satisfies the failed checks, keeping the user's intent and facts. "
           "Failed checks: " + ", ".join(fails or ["none"]) + ". Use a Goal / Don't touch / Done-when layout only if it helps. "
           "Never invent facts: put [ASK: ...] where the user must supply one. "
           "Output exactly: AFTER: <prompt> then WHY: <2 short lines>.\n\nPROMPT:\n" + text[:4000])
    return ask_claude(ask, timeout=timeout)

def rewrite(text, fails):
    try:
        return _rewrite_ask(text, fails)
    except RuntimeError as e:
        return f"(rewrite skipped: {e})"

# --- auto-rewrite: opt-in, runs in a detached background process so the statusline never blocks ------
CACHE = os.path.join(STATE, "last-rewrite.json")

def setting(name, default=None):
    try:
        with open(USER_CFG, encoding="utf-8") as f: return json.load(f).get(name, default)
    except (OSError, ValueError, AttributeError):
        return default

def set_setting(name, value):
    try:
        with open(USER_CFG, encoding="utf-8") as f: d = json.load(f)
        if not isinstance(d, dict): d = {}
    except (OSError, ValueError):
        d = {}
    d[name] = value
    os.makedirs(STATE, exist_ok=True)
    with open(USER_CFG, "w", encoding="utf-8") as f: json.dump(d, f, indent=2)

def read_cache():
    try:
        with open(CACHE, encoding="utf-8") as f: d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}

def write_cache(d):
    os.makedirs(STATE, exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f)
    os.replace(tmp, CACHE)

def prompt_key(row):
    import hashlib
    return f"{row[0]}:{hashlib.sha1(row[2].encode('utf-8')).hexdigest()[:12]}"

def spawn_bg(key):
    """Mark the prompt pending (so the next tick does not spawn again), then start a detached rewrite."""
    write_cache({"key": key, "status": "pending", "ts": time.time()})
    kw = {"creationflags": 0x00000008 | 0x00000200 | 0x08000000} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--bg-rewrite"], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)

def bg_rewrite(path):
    rows = load(path); i, fails = last_eval(rows)
    if i is None or not fails or llm_off(rows[i][1]): return
    key = prompt_key(rows[i])
    try: res = {"key": key, "status": "done", "text": _rewrite_ask(redact(rows[i][2]), fails, timeout=90)}
    except RuntimeError as e: res = {"key": key, "status": "failed", "error": str(e)[:80]}
    if read_cache().get("key") == key: write_cache({**res, "ts": time.time()})

def _after_lines(text, width=96):
    import textwrap
    m = re.search(r"AFTER:\s*(.*?)(?:\n\s*WHY:\s*(.*))?$", text, re.S)
    after, why = (m.group(1), m.group(2) or "") if m else (text, "")
    wrapped = [w for ln in after.splitlines() if ln.strip() for w in textwrap.wrap(ln.strip(), width - 7)] or [""]  # keep the model's line structure
    out = ["AFTER: " + wrapped[0]] + ["       " + w for w in wrapped[1:8]]
    if len(wrapped) > 8: out[-1] = out[-1][:width - 1] + "…"
    why = " ".join(why.split())
    return out + (["WHY:   " + why[:width - 7] + ("…" if len(why) > width - 7 else "")] if why else [])

def auto_after(rows, i, fails):
    """Statusline lines for the AFTER block, or []. Starts the background rewrite once per flagged prompt."""
    if not fails or not setting("auto_rewrite", False) or llm_off(rows[i][1]): return []
    key = prompt_key(rows[i]); c = read_cache(); age = time.time() - c.get("ts", 0)
    if c.get("key") != key:
        spawn_bg(key); return ["AFTER: (writing a better version...)"]
    if c.get("status") == "done": return _after_lines(c.get("text", ""))
    if c.get("status") == "pending" and age < 150: return ["AFTER: (writing a better version...)"]
    return ["AFTER: (unavailable: " + c.get("error", "timed out") + "; /coach retries)"]

LEARNED = os.path.join(STATE, "learned.json")  # written by review.py from YOUR history; read locally, no LLM

def has_kw(text, kw):
    """Whole-word/phrase match on lowercased text, so 'diff' does not fire on 'different'."""
    return re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", text) is not None

def learned():
    try:
        with open(LEARNED, encoding="utf-8") as f: d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}

def habit_note(text):
    """One line if the prompt matches a mistake or repeated request that review.py learned from your history."""
    low = text.lower(); d = learned()
    for m in d.get("mistakes", []):
        if any(has_kw(low, k) for k in m.get("keywords", [])): return f"habit: {m['name']} - {m.get('fix', '')}"[:160]
    for r in d.get("requests", []):
        if any(has_kw(low, k) for k in r.get("keywords", [])):
            return f"repeat request: {r['name']} (asked {r.get('count', '?')}x; /coach review can draft a skill)"
    return None

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
    print(("ok   " if setting("auto_rewrite", False) else "off  ") + "auto-rewrite in the statusline (opt in: setup.py --auto-rewrite on)")
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
    ap.add_argument("--bg-rewrite", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.bg_rewrite: bg_rewrite(a.history)
    elif a.doctor: doctor(a.history)
    elif a.coach: coach(a.history, llm=not a.no_llm)
    else:
        report(a.history)
        if a.show:
            print("\nREJECTION FLAGS")
            prev = None
            for ts, _proj, t in load(a.history):
                gap = None if prev is None else ts - prev; prev = ts
                if scorable(t) and not r5_rejection(t, gap): print("  -", redact(t)[:110])
