"""coachline - score your last Claude Code prompt against 5 rules, spot repeated requests.

Stdlib only. Reads <config>/history.jsonl, and a desktop app session's transcript, which has its prompts instead (read-only).
Writes only under <config>/coach/.
  python coach.py              replay report over your whole history
  python coach.py --coach      before/after for your last prompt (Haiku rewrite via `claude -p`)
  python coach.py --doctor     check that everything this tool depends on works
"""
import argparse, collections, datetime as dt, fnmatch, glob, json, os, platform, re, shutil, subprocess, sys, tempfile, time

CONFIG = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
HIST = os.path.join(CONFIG, "history.jsonl")
STATE = os.path.join(CONFIG, "coach")  # survives plugin updates; the plugin dir does not
OFF = os.path.join(STATE, "llm-off.txt")        # one path substring per line: never sent to an LLM
USER_CFG = os.path.join(STATE, "config.json")    # {"categories": {"name": "regex"}}
PASTE = re.compile(r"\[Pasted text #\d+ \+(\d+) lines\]")
BARE = re.compile(r"^(continue|yes|ok|confirm|go ahead|keep going|resume|clear)\W*$", re.I)
# Claude Code's own commands: settings and housekeeping, never a task, even with arguments (/plugin install x, /model sonnet).
# A skill or custom command called with a task (/frontend-design make it premium) is still a prompt.
BUILTIN = re.compile(r"^/(add-dir|agents|bug|clear|compact|config|context|cost|doctor|effort|exit|export|fast|help|hooks|ide|login|logout|"
                     r"mcp|memory|model|output-style|permissions|plugins?|release-notes|reload-plugins|resume|rewind|status|statusline|"
                     r"terminal-setup|theme|upgrade|usage|vim)(\s|$)", re.I)

_SECRETS = [
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>"),
    (r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<guid>"),
    (r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}\b", "<jwt>"),
    (r"\b(sk|pk|ghp|gho|ghs|xox[bap]|AKIA)[-_A-Za-z0-9]{16,}", "<key>"),
    (r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{16,}", "<token>"),
    (r"(?i)\b(password|passwd|pwd|secret|accountkey|sharedaccesskey|api[_-]?key|token)\s*[=:]\s*\S+", "<secret>"),
    (r"(?i)\b\w*_(password|passwd|pwd|secret|token|key)\w*\s*[=:]\s*\S+", "<secret>"),          # DB_PASSWORD=…, GITHUB_TOKEN: …
    (r"(?i)\b(password|passcode|passphrase|pin)\s+(is|was)\s+\S+", "<secret>"),
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

# --- vagueness: 0 (concrete) .. 1 (nothing to act on). Local, no LLM; held to tests/vague_cases.jsonl (precision >= 0.9) ---------
EXT = r"py|pyi|ts|tsx|js|jsx|mjs|go|rs|md|json|ya?ml|toml|java|kt|rb|php|cs|cpp|cc|c|h|hpp|sh|ps1|sql|css|scss|html|vue|svelte|swift|tf|lock|env|txt|csv"
ANCHOR = re.compile(r"`[^`]+`|https?://\S+|\b[A-Z][A-Z0-9]+-\d+\b|(?<![\w.-])[\w.-]*/[\w./-]+|(?<![\w-])[\w-]+\.(?:" + EXT + r")\b|\b[a-z]+[A-Z]\w*\b"
                    r"|\b[A-Za-z0-9]+_\w+\b|\b\w*(?:Error|Exception)\b|\b\d+(?:\.\d+)*(?:%|ms|s|px|[kmg]b|x)?\b|'[^'\s][^']{2,}'|\"[^\"]{3,}\"|=")
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")   # no spaces between words: about two characters a word
DEICTIC = re.compile(r"\b(it|this|that|them|everything|the thing)\b", re.I)

def vagueness(text):
    """How little the prompt gives Claude to act on: short, no anchor (file, path, identifier, error, number, ticket, link), soft
    qualifiers, 'it/this' pointing at nothing. A paste or two anchors make it concrete."""
    b = body(text); words = len(b.split()) + len(CJK.findall(b)) // 2
    anchors = len(ANCHOR.findall(b[:2000]))                # a prompt's anchors are near its start; a minified paste must not stall a frame
    s = 0.5 if words < 8 else 0.25 if words < 14 else 0.0
    if not anchors:
        s += 0.35
        if DEICTIC.search(b): s += 0.15
    if not r4_qualifiers(text): s += 0.25
    s -= 0.3 * min(anchors, 2)
    if words > 25 and r1_done_when(text): s -= 0.3       # a long prompt that says what done looks like
    if PASTE.search(text): s -= 0.6
    return max(0.0, min(1.0, s))

def vague(text):
    return vagueness(text) >= 0.6

HINTS = [   # (the hint, why it matters: shown to beginners)
    ("replace 'best/properly/clean' with a rule you can check", "so Claude knows what good means here"),
    ("say what 'it' or 'this' is: a file, a function, an error", "so Claude doesn't pick the wrong thing"),
    ("name a file, function, error or number", "so Claude doesn't have to guess"),
    ("say what done looks like", "so Claude knows when to stop"),
]

def hint_for(text, beginner=False):
    """The one thing a vague prompt lacks most, as the hint under the prompt box says it (with why, for a beginner); None when the
    prompt is concrete enough."""
    b = body(text)[:2000]
    if not b.strip() or not vague(text): return None
    anchored = bool(ANCHOR.search(b))
    n = 0 if not r4_qualifiers(text) else 1 if DEICTIC.search(b) and not anchored else 2 if not anchored else 3
    return HINTS[n][0] + (" — " + HINTS[n][1] if beginner else "")

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

def prompts_path():
    """Prompts of the sessions Claude Code keeps out of history.jsonl (the desktop app's), in its format: see sync_transcript."""
    return os.path.join(STATE, "prompts.jsonl")

def _records(path):
    """A JSON-lines file's records. Skips malformed lines; history.jsonl is not a public format."""
    try:
        f = open(path, encoding="utf-8")
    except OSError:
        return
    with f:
        for l in f:
            try: r = json.loads(l)
            except ValueError: continue
            if isinstance(r, dict): yield r

def _history(path):
    """history.jsonl's records, and with it prompts.jsonl's."""
    yield from _records(path)
    if path == HIST: yield from _records(prompts_path())

def load(path):
    """Rows of (unix_seconds, project, text). Skips malformed lines."""
    rows = []
    for r in _history(path):
        try: rows.append((float(r["timestamp"]) / 1000, r.get("project") or "", str(r["display"]).strip()))
        except (ValueError, KeyError, TypeError, AttributeError): continue
    return sorted(rows)

def load_full(path):
    """(unix_seconds, project, text, session_id) rows, oldest first. Malformed lines are skipped."""
    rows = []
    for r in _history(path):
        try: rows.append((float(r["timestamp"]) / 1000, r.get("project") or "", str(r["display"]).strip(), str(r.get("sessionId") or "")))
        except (ValueError, KeyError, TypeError, AttributeError): continue
    return sorted(rows)

# the app's own blocks in a prompt's content (its context, a command's markup), not what you typed
TAGGED = re.compile(r"^\s*<(system-reminder|command-[a-z-]+|local-command-[a-z-]+|ide_[a-z_]+)>")

def transcript_prompts(session):
    """[(ms, project, text)] of what you typed in a session, from its transcript (read-only): a person's rows only (origin
    human), not tool results, meta rows or a subagent's."""
    out = []
    for p in glob.glob(os.path.join(CONFIG, "projects", "*", session + ".jsonl")):
        try:
            f = open(p, encoding="utf-8")
        except OSError:
            continue
        with f:
            for l in f:
                if '"human"' not in l: continue                # most rows are tool calls: skip them unparsed
                try:
                    r = json.loads(l)
                    if r.get("type") != "user" or (r.get("origin") or {}).get("kind") != "human" or r.get("isMeta") or r.get("isSidechain"): continue
                    c = r["message"]["content"]
                    parts = [c] if isinstance(c, str) else [b.get("text") or "" for b in c if isinstance(b, dict) and b.get("type") == "text"]
                    text = "\n".join(t for t in parts if t.strip() and not TAGGED.match(t)).strip()
                    ms = int(dt.datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).timestamp() * 1000)
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
                if text: out.append((ms, r.get("cwd") or "", text))
    return out

def sync_transcript(session, rows):
    """A session that history.jsonl has no line of (the desktop app and the editors write none): its prompts from its transcript,
    added to prompts.jsonl once each, so this thread's pane, the analysis and the review read them as any other. `rows` are
    load_full(HIST)'s. True when it added one."""
    have = {(r.get("timestamp"), r.get("display")) for r in _records(prompts_path()) if r.get("sessionId") == session}
    if any(r[3] == session and (round(r[0] * 1000), r[2]) not in have for r in rows): return False   # history.jsonl has it
    new = [(ms, proj, text) for ms, proj, text in transcript_prompts(session) if (ms, text) not in have]
    if not new: return False
    os.makedirs(STATE, exist_ok=True)
    with open(prompts_path(), "a", encoding="utf-8") as f:
        for ms, proj, text in new:
            f.write(json.dumps({"display": text, "pastedContents": {}, "timestamp": ms, "project": proj, "sessionId": session}) + "\n")
    return True

def scorable(t):
    return not (BARE.match(t) or re.match(r"^/\S+$", t) or BUILTIN.match(t) or len(body(t).split()) < 3)

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

NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}   # CREATE_NO_WINDOW: a child console program must never pop up a terminal

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
                           input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           cwd=tempfile.gettempdir(), **NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude timed out after {timeout}s")
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError((f"{r.stderr or ''} {r.stdout or ''}".strip() or "claude returned nothing")[:300])   # a limit notice may be on either
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
        try: return subprocess.run(argv, input=data, capture_output=True, timeout=10, **NO_WINDOW).returncode == 0
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
STALE_DAYS = 7          # a per-tab or per-session file untouched this long belongs to a tab or session that is gone
REWRITES_KEEP = 5000    # rewrites.jsonl keeps its newest lines; later lines win anyway
SWEPT = ("current-session-*.json", "watch-*.alive", "watch-*.launching", "pane-*.json", "pane-*.lock")
OUTCOMES = os.path.join(STATE, "outcomes.jsonl")   # turns you interrupted, prompts your next one corrected: one line each, kept OUTCOME_DAYS
OUTCOME_DAYS = 90
CORRECTION_WORDS = 6
# a follow-up that says the last prompt was misread. Not REJECT: "still failing" is about the code, not the prompt
# "no"/"nope" only on their own ("no, …", "No."): "no worries", "no need to…", "no-op" are not corrections; nor "actually also…"
CORRECTION = re.compile(r"^((no|nope)(?=\s*[,.!;:]|\s*$)|that['\u2019]?s (wrong|not)\b|not what i\b|not quite\b|(wait,?\s+)?i meant\b|undo that\b)", re.I)

def is_correction(text):
    return bool(CORRECTION.match(" ".join(re.sub(r"^\W+", "", body(text)).split()[:CORRECTION_WORDS])))

def record_outcome(kind, prompt, now=None):
    """One line in outcomes.jsonl: when, what happened, how vague the prompt was, its first words redacted. Never the prompt itself.
    Commands (/clear, !ls, # note) and bare replies are not prompts. One write of one line: several tabs may append at once."""
    t = prompt.strip()
    if t[:1] in ("/", "!", "#") or not scorable(t): return False
    now = time.time() if now is None else now
    head = " ".join(redact(body(t)).split()[:4])
    if kind == "corrected" and any(o.get("kind") == "aborted" and o.get("head") == head and abs(o["ts"] - now) < 600 for o in outcomes(1, now)):
        return False                                          # stopped, then "no, I meant…": one rework, not two
    v = vagueness(t)
    line = json.dumps({"v": 1, "ts": now, "kind": kind, "vague": v >= 0.6, "cells": round(5 * (1 - v)), "head": head})
    append_line(OUTCOMES, line)
    return True

def append_line(path, line):
    """Append one line whole while other processes append too. POSIX O_APPEND writes are atomic; Windows seeks then writes, so
    there the first byte is locked around the write (msvcrt.locking retries for up to ~10 s, then raises)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = (line + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    try:
        if os.name != "nt": os.write(fd, data); return
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET); msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        try:
            os.lseek(fd, 0, os.SEEK_END); os.write(fd, data)
        finally:
            os.lseek(fd, 0, os.SEEK_SET); msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(fd)

def outcomes(days, now=None):
    cut = (time.time() if now is None else now) - days * 86400
    try:
        with open(OUTCOMES, encoding="utf-8") as f: rows = [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError): return []
    return [r for r in rows if isinstance(r, dict) and isinstance(r.get("ts"), (int, float)) and r["ts"] >= cut]

EVIDENCE_MIN, EVIDENCE_DAYS = 3, 14

def evidence_line(rows, now=None):
    """Rework (interrupts, corrections) after vague prompts vs concrete ones, out of your prompts of each kind in the same 14 days.
    rows: history as load_full gives it. None until there are EVIDENCE_MIN events: a rate of two is an anecdote."""
    now = time.time() if now is None else now
    ev = outcomes(EVIDENCE_DAYS, now)
    if len(ev) < EVIDENCE_MIN: return None
    cut = now - EVIDENCE_DAYS * 86400
    sent = [vague(r[2]) for r in rows if r[0] >= cut and r[2].strip()[:1] not in ("/", "!", "#") and scorable(r[2])]
    a = sum(1 for e in ev if e.get("vague")); b = len(ev) - a
    n = max(sum(sent), a); m = max(len(sent) - sum(sent), b)          # an event whose prompt is older than history still counts
    return f"Vague prompts led to rework {a} of {n} times in {EVIDENCE_DAYS} days; concrete ones {b} of {m}"

def _rewrite(path, keep):
    """Rewrite a line log with keep(lines) -> lines, unless a line was appended meanwhile (then next time). Never raises."""
    try:
        size = os.path.getsize(path)
        with open(path, encoding="utf-8") as f: lines = f.readlines()
    except OSError: return
    kept = keep(lines)
    if kept == lines: return
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f: f.writelines(kept)
        if os.path.getsize(path) == size: _replace(tmp, path)
    except OSError: pass
    finally:
        try: os.remove(tmp)
        except OSError: pass

def _recent(cut):
    def keep(lines):
        out = []
        for l in lines:
            try: ts = json.loads(l).get("ts", 0)
            except (ValueError, AttributeError): continue
            if isinstance(ts, (int, float)) and ts >= cut: out.append(l)
        return out
    return keep

def sweep(now=None):
    """SessionStart housekeeping: delete stale per-tab / per-session files and cut rewrites.jsonl to its newest REWRITES_KEEP lines.
    The shared files (watch.alive, current-session.json, ...) and your settings are never touched. Returns the names removed."""
    cut = (time.time() if now is None else now) - STALE_DAYS * 86400; gone = []
    def tab_in_use(p):                               # current-session-<tab>.json lives as long as its tab's panel does
        return panel_alive(max_age=STALE_DAYS * 86400, tab=os.path.basename(p)[len("current-session-"):-len(".json")])
    for pat in SWEPT:
        for p in glob.glob(os.path.join(STATE, pat)):
            try:
                if os.path.getmtime(p) < cut and not (pat.startswith("current-session") and tab_in_use(p)): os.remove(p); gone.append(os.path.basename(p))
            except OSError: pass
    _rewrite(REWRITES, lambda lines: lines[-REWRITES_KEEP:])
    _rewrite(OUTCOMES, _recent((time.time() if now is None else now) - OUTCOME_DAYS * 86400))
    import library                                    # here, not at the top: library imports this module
    library.promote_due(now)
    return gone

def tab_key(env=None):
    """The Windows Terminal tab Claude Code runs in (each has its own WT_SESSION), as a file-name part; '' outside Windows Terminal.
    Each tab gets its own panel, which shows the conversation of that tab."""
    return re.sub(r"[^0-9A-Za-z-]", "", (os.environ if env is None else env).get("WT_SESSION", ""))[:64]

def per_tab(path, tab):
    """watch.alive -> watch-<tab>.alive: one file per tab, the shared one when there is no tab."""
    if not tab: return path
    base, ext = os.path.splitext(path)
    return f"{base}-{tab}{ext}"

def panel_alive(max_age=6, tab=""):
    try: return time.time() - os.path.getmtime(per_tab(ALIVE, tab)) < max_age
    except OSError: return False

def session_file():
    return os.path.join(STATE, "current-session.json")

def record_session(raw, tab=""):
    """The SessionStart hook's JSON (it names the session that just started or resumed) -> current-session.json, so the panel knows a fresh
    session is the one you are in before it has a single prompt or transcript. Silent on anything unexpected."""
    try:
        d = json.loads(raw)
        sid = d.get("session_id")
        if not (isinstance(sid, str) and re.fullmatch(r"[0-9A-Za-z-]{8,64}", sid)): return
        if tab and d.get("source") in ("startup", "resume", "clear"):    # this tab's panel shows exactly this session, resumed ones too
            write_json(per_tab(session_file(), tab), {"id": sid, "ts": time.time()})
        if d.get("source") not in ("startup", "clear"): return      # a resumed session is found by its transcript; only a brand-new one needs announcing
        write_json(session_file(), {"id": sid, "ts": time.time(), "source": str(d.get("source", ""))[:20]})
    except (ValueError, AttributeError, OSError):
        pass

def started_session(tab=""):
    """(session id, when) the hook last recorded (in this Windows Terminal tab, when `tab` is given), or None."""
    try:
        with open(per_tab(session_file(), tab), encoding="utf-8") as f: d = json.load(f)
        return (d["id"], float(d["ts"])) if isinstance(d["id"], str) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None

def write_json(path, d, stamp=True, indent=None):
    """Write whole or not at all: a panel, a hook or a background job may be reading it. stamp adds "v": 1 (coachline's own files
    only; never Claude's settings.json). Readers ignore "v": a file without one is a 0.17 file and reads the same."""
    if stamp: d = {**d, "v": 1}
    path = os.path.realpath(path)                    # a settings.json linked from a dotfiles repo stays a link
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f, indent=indent)
        _replace(tmp, path)
    except BaseException:
        try: os.remove(tmp)
        except OSError: pass
        raise

def _replace(tmp, path):
    for i in range(5):                                # Windows refuses to replace a file another process is reading: wait a moment
        try:
            os.replace(tmp, path); return
        except PermissionError:
            if i == 4: raise
            time.sleep(0.05 * (i + 1))

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
    write_json(USER_CFG, d, indent=2)

MODELS = ("haiku", "sonnet", "opus")

def defaults_on():
    """macOS and Linux: the panel opens by itself until the user turns that off. Windows keeps auto-open opt-in.
    COACHLINE_PLATFORM overrides the system name (tests)."""
    return (os.environ.get("COACHLINE_PLATFORM") or platform.system()) != "Windows"

def ai_on():
    """Claude analysis (advice per prompt, review of your history). On by default everywhere; 'auto_rewrite' is its old name."""
    v = setting("panel_ai")
    if v is None: v = setting("auto_rewrite")
    return True if v is None else bool(v)

def research_on():
    """Web research once per new task (the slower second pass). On wherever analysis is on; 'discover' is its old name."""
    v = setting("research")
    if v is None: v = setting("discover")
    return ai_on() and (True if v is None else bool(v))

def model_for(kind):
    """The model of a pass: 'fast' (advice and the enhanced prompt, default haiku) or 'research' (web research, default sonnet)."""
    v = setting("model_" + kind)
    return v if v in MODELS else {"fast": "haiku", "research": "sonnet"}[kind]

def auto_open_on():
    """The panel opens by itself at session start: the Claude Code pane on macOS / Linux, a Windows Terminal split on Windows."""
    v = setting("auto_open_watch")
    return bool(defaults_on() if v is None else v)

BEGINNER_PROMPTS = 50

def level():
    """'beginner' or 'pro': the setting when it is one of those, else beginner until your history holds BEGINNER_PROMPTS prompts.
    Reads history only as far as it needs: this runs on every pause in typing."""
    v = setting("level")
    if v in ("beginner", "pro"): return v
    n = 0
    try:
        with open(HIST, encoding="utf-8", errors="replace") as f:
            for line in f:
                try: t = json.loads(line).get("display", "")
                except (ValueError, AttributeError): continue
                if isinstance(t, str) and scorable(t):
                    n += 1
                    if n >= BEGINNER_PROMPTS: return "pro"
    except OSError: pass
    return "beginner"

def hold_on():
    """Hold a clearly vague prompt at Enter (the Claude Code pane; a second Enter sends it). Off unless you switch it on."""
    return bool(setting("hold", False))

def hints_on():
    """The hint under the prompt box as you type (the Claude Code pane): on unless switched off. Local; nothing is sent."""
    v = setting("hints")
    return True if v is None else bool(v)

def motion_on(env=None):
    """The panel's motion (shimmer, reveal, Copied flash, meter fill). On unless switched off, NO_COLOR is set, or over SSH, where
    every frame crosses the network."""
    env = os.environ if env is None else env
    if env.get("NO_COLOR") or env.get("SSH_CONNECTION") or env.get("SSH_TTY"): return False
    v = setting("motion")
    return True if v is None else bool(v)

NOTICE = "Claude analysis is on: prompts go redacted to your subscription, task topics to web search · /coach panel-ai off"
NOTICE_SESSIONS = 3

def notice(session):
    """The first-run line, while analysis is on only because of the default (the user never chose), in their first three
    sessions. Shown by the Claude Code pane and by watch.py alike."""
    if not ai_on() or setting("panel_ai") is not None or setting("auto_rewrite") is not None: return None
    seen = setting("notice_sessions", [])
    if not isinstance(seen, list): seen = []
    if session in seen: return NOTICE
    if len(seen) >= NOTICE_SESSIONS: return None
    try: set_setting("notice_sessions", seen + [session])
    except OSError: pass
    return NOTICE

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
    # Not DETACHED_PROCESS: Windows then ignores CREATE_NO_WINDOW and gives the `claude` child its own visible console.
    # With a hidden console the job owns, claude inherits it and nothing appears.
    kw = {"creationflags": 0x00000200 | 0x08000000} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)

def spawn_key(key):
    """Analyse one specific prompt in a detached process."""
    _spawn([sys.executable, os.path.abspath(__file__), "--bg-rewrite", "--key", key])

def spawn_review():
    """Have Claude analyse your whole history (review.py) in a detached process."""
    _spawn([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "review.py"), "--yes", "--days", "90", "--max", "360"])

def spawn_research(key):
    """Search the web again for one analysed prompt (the panel's r key), in a detached process. Ignores the cache and a usage-limit pause."""
    _spawn([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "discover.py"), "--key", key])

def _save(key, res):
    os.makedirs(STATE, exist_ok=True)
    if res["status"] == "done":
        rec = {"key": key, "text": res["text"], "advice": res["advice"]}
        if res.get("discovery"): rec["discovery"] = res["discovery"]
    else:
        rec = {"key": key, "error": res.get("error", "failed")}
    with open(REWRITES, "a", encoding="utf-8") as f: f.write(json.dumps(rec) + "\n")

def _save_discovery(key, advice, items):
    """Research results for the prompt with this key (maybe another job's: the research queue runs the newest request)."""
    _save(key, {"key": key, "status": "done", "advice": advice, "text": "AFTER: " + advice.get("after", ""), "discovery": items})

def bg_rewrite(path, key):
    """Claude's analysis of the prompt with this key (advice and enhanced prompt, then web research when it starts a new task), appended to rewrites.jsonl."""
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
    if res["status"] == "done" and research_on():
        import discover, stackinfo
        if discover.wanted(rows[i][3], res["advice"]):          # once per new task; follow-ups of the same task send nothing
            discover.request(key, rows[i][3], res["advice"], stackinfo.detect(rows[i][1]), _save_discovery)

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

KEPT = ("config.json", "llm-off.txt",   # your settings: forgetting llm-off.txt would start sending a project you kept private
        "panel.py", "*.running", "*.launching")   # the panel's launcher, and the locks of jobs running now

def data_usage():
    """(files, bytes) coachline keeps under STATE."""
    n = size = 0
    for root, _dirs, files in os.walk(STATE):
        for name in files:
            try: size += os.path.getsize(os.path.join(root, name)); n += 1
            except OSError: pass
    return n, size

def forget(what):
    """Delete what coachline learned and cached: 'all' is everything but your settings (KEPT), 'outcomes' the outcome log only,
    'library' the saved prompts and their candidates.
    Returns the paths removed."""
    if what in ("outcomes", "library"):
        gone = []
        for p in ([OUTCOMES] if what == "outcomes" else [os.path.join(STATE, n) for n in ("library.json", "library-pending.json", "library-vetoes.json")]):
            try: os.remove(p); gone.append(p)
            except OSError: pass
        return gone
    if what != "all": raise ValueError(what)
    gone = []
    for root, dirs, files in os.walk(STATE, topdown=False):
        for name in files:
            p = os.path.join(root, name)
            if root == STATE and any(fnmatch.fnmatch(name, k) for k in KEPT): continue
            try: os.remove(p); gone.append(p)
            except OSError: pass
        for name in dirs:
            try: os.rmdir(os.path.join(root, name))
            except OSError: pass
    return gone

def size_text(n):
    return f"{n / 1024:.0f} KB" if n < 10 * 1024 * 1024 else f"{n / 1024 / 1024:.0f} MB"

def doctor(path):
    ok = True
    def line(good, msg):
        nonlocal ok; ok &= good; print(("ok   " if good else "FAIL ") + msg)
    rows = load(path)
    line(os.path.isfile(path), f"history file: {path}")
    line(bool(rows), f"parsed {len(rows)} prompts (needs JSONL with 'display' and 'timestamp' fields)")
    line(sys.version_info >= (3, 9), f"python {sys.version.split()[0]} at {sys.executable}")
    print(("ok   " if shutil.which("claude") else "warn ") + "claude CLI on PATH (needed only for the /coach rewrite)")
    def switch(on, msg, flag):  # the hint names the way to the other state
        to = "off" if on else "on"
        print(("ok   " if on else "off  ") + f"{msg} (turn {to}: " + py_cmd("setup.py", flag, to) + ")")
    switch(ai_on(), "Claude analysis in the panel", "--panel-ai")
    switch(research_on(), f"web research per new task, {model_for('research')}", "--research")
    switch(auto_open_on(), "panel opens itself at session start", "--auto-open")
    n, size = data_usage()
    print(f"ok   coachline data: {n} file{'s' if n != 1 else ''}, {size_text(size)} in {STATE} (wipe: {py_cmd('coach.py', '--forget', 'all')})")
    print("     open the panel by hand: " + py_cmd("watch.py"))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(); ap.add_argument("--history", default=HIST)
    ap.add_argument("--coach", action="store_true"); ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--doctor", action="store_true"); ap.add_argument("--show", action="store_true", help="list rejection-rule hits")
    ap.add_argument("--bg-rewrite", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--key", help=argparse.SUPPRESS); ap.add_argument("--copy", action="store_true", help="with --coach: copy the enhanced prompt to the clipboard")
    ap.add_argument("--forget", metavar="all|outcomes|library", help="delete what coachline keeps (all: except your settings and llm-off.txt)")
    a = ap.parse_args()
    if a.forget is not None:
        if a.forget not in ("all", "outcomes", "library"): print("usage: coach.py --forget all|outcomes|library"); sys.exit(2)
        before = data_usage()[1]; gone = forget(a.forget)
        print(f"removed {len(gone)} files ({size_text(before - data_usage()[1])})" + ("; kept your settings and llm-off.txt" if a.forget == "all" else ""))
    elif a.bg_rewrite:
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
