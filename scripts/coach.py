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
        with open(USER_CFG, encoding="utf-8") as f: extra = json.load(f).get("categories", {})
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

def ask_claude(prompt, model="haiku", timeout=180, web=False):
    """One-shot question to the user's own Claude subscription via `claude -p`. No API key, no settings, no session
    saved, and no tools, except that web=True allows exactly two read-only ones: WebSearch and WebFetch. The prompt goes over stdin (no argv length limit, not visible in `ps`).
    COACHLINE_CLAUDE overrides the command (used by the tests). Returns text; raises RuntimeError on failure."""
    import shlex
    cmd = shlex.split(os.environ.get("COACHLINE_CLAUDE") or "claude") or ["claude"]  # use forward slashes in COACHLINE_CLAUDE
    if not os.environ.get("COACHLINE_CLAUDE") and not shutil.which(cmd[0]):
        raise RuntimeError("`claude` CLI not on PATH")
    try:
        r = subprocess.run(cmd + ["-p", "--model", model, "--no-session-persistence", "--disable-slash-commands",
                                  "--tools", "WebSearch,WebFetch" if web else "", "--setting-sources", ""]
                                 + (["--allowedTools", "WebSearch,WebFetch"] if web else []),
                           input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                           cwd=tempfile.gettempdir())
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude timed out after {timeout}s")
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError((r.stderr or r.stdout or "claude returned nothing").strip()[:300])
    return r.stdout.strip()

_ESC = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b.")

def clean(s, keep_newlines=False):
    """Text from a model or the web goes to a terminal: strip escape sequences and control characters first."""
    s = _ESC.sub("", str(s))
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]" if keep_newlines else r"[\x00-\x1f\x7f-\x9f]", " ", s)
    return s if keep_newlines else re.sub(r"\s+", " ", s).strip()

def _win_clip(text):
    """Windows: put text on the clipboard through the Win32 API. Exact, no byte-order mark, no subprocess."""
    try:
        import ctypes
        from ctypes import wintypes
        k, u = ctypes.windll.kernel32, ctypes.windll.user32
        k.GlobalAlloc.restype = wintypes.HGLOBAL; k.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        k.GlobalLock.restype = ctypes.c_void_p; k.GlobalLock.argtypes = [wintypes.HGLOBAL]; k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        u.OpenClipboard.argtypes = [wintypes.HWND]; u.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        data = (text.replace("\r\n", "\n").replace("\n", "\r\n") + "\0").encode("utf-16-le")   # CF_UNICODETEXT wants CRLF and a NUL
        h = k.GlobalAlloc(0x0002, len(data)); ptr = k.GlobalLock(h)
        if not h or not ptr: return False
        ctypes.memmove(ptr, data, len(data)); k.GlobalUnlock(h)
        for _ in range(20):
            if u.OpenClipboard(None): break
            time.sleep(0.05)
        else:
            return False
        try:
            u.EmptyClipboard()
            return bool(u.SetClipboardData(13, h))    # on success the system owns the memory
        finally:
            u.CloseClipboard()
    except (OSError, AttributeError, ValueError):
        return False

def copy_text(text):
    """Put text on the system clipboard exactly as given. Returns the method used, or None. Stdlib only.
    COACHLINE_CLIPBOARD (a command reading stdin) overrides everything; the tests use it so they never touch a real clipboard."""
    import base64, shlex
    def run(argv, data):
        try: return subprocess.run(argv, input=data, capture_output=True, timeout=10).returncode == 0
        except (OSError, subprocess.TimeoutExpired): return False
    if os.environ.get("COACHLINE_CLIPBOARD"):
        return "override" if run(shlex.split(os.environ["COACHLINE_CLIPBOARD"]), text.encode("utf-8")) else None
    if os.name == "nt" and _win_clip(text): return "the Windows clipboard"
    # clip.exe (WSL via interop, or a failed API call): UTF-16LE with NO byte-order mark; a BOM is copied as a stray U+FEFF character
    if shutil.which("clip.exe") and run(["clip.exe"], text.encode("utf-16-le")): return "clip.exe"
    if sys.platform == "darwin" and shutil.which("pbcopy") and run(["pbcopy"], text.encode("utf-8")): return "pbcopy"
    for argv in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
        if shutil.which(argv[0]) and run(argv, text.encode("utf-8")): return argv[0]
    if sys.stdout.isatty():  # OSC 52: Windows Terminal, iTerm2, kitty and tmux (with set-clipboard) copy on this sequence
        sys.stdout.write("\033]52;c;" + base64.b64encode(text.encode("utf-8")).decode() + "\a"); sys.stdout.flush()
        return "terminal (OSC 52)"
    return None

def advisable(text, fails):
    """Worth an LLM call: a rule fired, or it is long enough to be a real task (not 'continue' or 'yes')."""
    return bool(fails) or len(body(text).split()) >= 6

# --- Claude-driven analysis, started by the panel in detached background processes ------------------
ALIVE = os.path.join(STATE, "watch.alive")  # watch.py touches this every second while it is open
REWRITES = os.path.join(STATE, "rewrites.jsonl")  # append-only log of finished analyses, keyed by prompt_key; later lines win
REVIEW_LOCK = os.path.join(STATE, "review.running")  # review.py holds this while it runs

def panel_alive(max_age=6):
    try: return time.time() - os.path.getmtime(ALIVE) < max_age
    except OSError: return False

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

def ai_on():
    """Claude analysis (advice per prompt, review of your history) is opt-in. 'auto_rewrite' is the old name of the same switch."""
    v = setting("panel_ai")
    return bool(setting("auto_rewrite", False) if v is None else v)

def py_cmd(script, *args):
    """A command line the user can paste: this Python (python / python3 / full path), a script next to this file, arguments."""
    exe = sys.executable; name = None
    for n in ("python", "python3"):
        w = shutil.which(n)
        try:
            if w and os.path.samefile(w, exe): name = n; break
        except OSError: pass
    py = name or (f'"{exe}"' if " " in exe else exe)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script).replace("\\", "/")
    return " ".join([py, f'"{path}"' if " " in path else path, *args])

def prompt_key(row):
    import hashlib
    return f"{row[0]}:{hashlib.sha1(row[2].encode('utf-8')).hexdigest()[:12]}"

def _spawn(argv):
    kw = {"creationflags": 0x00000008 | 0x00000200 | 0x08000000} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)

def spawn_key(key):
    """Analyse one specific prompt in a detached process."""
    _spawn([sys.executable, os.path.abspath(__file__), "--bg-rewrite", "--key", key])

def spawn_review():
    """Have Claude analyse your whole history (review.py) in a detached process."""
    _spawn([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "review.py"), "--yes", "--days", "90", "--max", "360"])

def _save(key, res):
    os.makedirs(STATE, exist_ok=True)
    if res["status"] == "done":
        rec = {"key": key, "text": res["text"], "advice": res["advice"]}
        if res.get("discovery"): rec["discovery"] = res["discovery"]
    else:
        rec = {"key": key, "error": res.get("error", "failed")}
    with open(REWRITES, "a", encoding="utf-8") as f: f.write(json.dumps(rec) + "\n")

def bg_rewrite(path, key):
    """Claude's analysis of the prompt with this key (advice, enhanced prompt, optional web discovery), appended to rewrites.jsonl."""
    rows = load_full(path)
    i = next((n for n, r in enumerate(rows) if prompt_key(r) == key), None)
    if i is None or llm_off(rows[i][1]): return
    fails = [n for n, fn in RULES if not fn(rows[i][2], rows[i][0] - rows[i - 1][0] if i else None)]
    # the five earlier prompts of the same conversation: what "this" and "it" refer to (redacted; opted-out projects never included)
    context = [redact(r[2]) for r in rows[max(0, i - 40):i] if r[3] == rows[i][3] and scorable(r[2]) and not r[2].startswith("/coach") and not llm_off(r[1])][-5:]
    import advisor
    try:
        adv = advisor.advise(redact(rows[i][2]), fails, timeout=90, context=context)
        res = {"key": key, "status": "done", "advice": adv, "text": "AFTER: " + adv.get("after", "")}
    except (RuntimeError, ValueError) as e: res = {"key": key, "status": "failed", "error": str(e)[:80]}
    _save(key, res)
    if res["status"] == "done" and setting("discover", False):
        import discover
        items = discover.for_advice(res["advice"])  # cached per topic for 24h; verified locally; never raises
        if items: _save(key, {**res, "discovery": items})

def _after_lines(text, width=96):
    import textwrap
    m = re.search(r"AFTER:\s*(.*?)(?:\n\s*WHY:\s*(.*))?$", text, re.S)
    after, why = (m.group(1), m.group(2) or "") if m else (text, "")
    wrapped = [w for ln in after.splitlines() if ln.strip() for w in textwrap.wrap(ln.strip(), width - 7)] or [""]  # keep the model's line structure
    out = ["AFTER: " + wrapped[0]] + ["       " + w for w in wrapped[1:8]]
    if len(wrapped) > 8: out[-1] = out[-1][:width - 1] + "…"
    why = " ".join(why.split())
    return out + (["WHY:   " + why[:width - 7] + ("…" if len(why) > width - 7 else "")] if why else [])

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

def coach(path, llm=True, copy=False):
    rows = load(path); i, fails = last_eval(rows)
    if i is None: print("No scorable prompt found. Run `--doctor` to check your history file."); return
    _ts, proj, t = rows[i]
    print(f"BEFORE ({verdict(t, fails)}): {redact(t)[:400]}\n")
    for f in fails: print(f"  x {f}: {FIX[f]}")
    if not fails: print("  no rule fired" + (" (short prompt: most rules do not apply)" if verdict(t, fails) == "short" else ""))
    n = repeat_note(rows, i)
    if n: print(f"\nREPEAT: {n}. Draft skills are in {os.path.join(STATE, 'drafts')} (review, then move into your skills folder yourself).")
    if not llm: return
    if llm_off(proj): print(f"\n(LLM advice skipped: project matches an entry in {OFF})"); return
    import advisor
    try:
        adv = advisor.advise(redact(t), fails)
    except (RuntimeError, ValueError) as e:
        print(f"\n(advice skipped: {e})"); return
    print()
    for k, text in advisor.lines(adv, 100):
        if k != "after": print(text)                      # the enhanced prompt is printed once, below, as plain text
    if adv.get("after"):
        print("\n----- ENHANCED PROMPT (plain text; [ASK: ...] and <email>-style placeholders are for you to fill in) -----")
        print(adv["after"]); print("-" * 60)
        if copy:
            m = copy_text(adv["after"]); print(f"(copied to your clipboard via {m})" if m else "(no clipboard available here: select the text above)")

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
    print(("ok   " if ai_on() else "off  ") + "Claude analysis in the panel (turn on: " + py_cmd("setup.py", "--panel-ai", "on") + ")")
    print(("ok   " if setting("auto_open_watch", False) else "off  ") + "panel opens itself at session start (turn on: " + py_cmd("setup.py", "--auto-open", "on") + ")")
    print("     open the panel by hand: " + py_cmd("watch.py"))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(); ap.add_argument("--history", default=HIST)
    ap.add_argument("--coach", action="store_true"); ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--doctor", action="store_true"); ap.add_argument("--show", action="store_true", help="list rejection-rule hits")
    ap.add_argument("--bg-rewrite", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--key", help=argparse.SUPPRESS); ap.add_argument("--copy", action="store_true", help="with --coach: copy the enhanced prompt to the clipboard")
    a = ap.parse_args()
    if a.bg_rewrite:
        if a.key: bg_rewrite(a.history, a.key)
    elif a.doctor: doctor(a.history)
    elif a.coach: coach(a.history, llm=not a.no_llm, copy=a.copy)
    else:
        report(a.history)
        if a.show:
            print("\nREJECTION FLAGS")
            prev = None
            for ts, _proj, t in load(a.history):
                gap = None if prev is None else ts - prev; prev = ts
                if scorable(t) and not r5_rejection(t, gap): print("  -", redact(t)[:110])
