"""library.py - prompts that worked first time, kept on this machine and offered again for a similar draft.

A prompt becomes a candidate when its turn ends normally (the pane module's `pane.py --outcome done`). Your next prompts decide:
a correction ("no, I meant…") drops it, CLEAN_FOLLOWUPS clean ones save it, and so does a day without a correction.
<state>/library-pending.json  {"items": [{"text", "project", "ts", "clean"}]}  newest last
<state>/library.json          {"items": [{"id", "text", "project", "stack", "ts", "uses", "off"}]}
Texts are redacted before they are written. Nothing here is ever sent anywhere.
"""
import contextlib, hashlib, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach, stackinfo

LIBRARY_MIN_WORDS, CLEAN_FOLLOWUPS, PENDING_DAYS, PENDING_MAX = 12, 2, 1, 20
MATCH, CAP_PROJECT, CAP_GLOBAL = 0.6, 200, 500
LIB, PENDING, VETOES = "library.json", "library-pending.json", "library-vetoes.json"
MIN_CONTENT = 4       # an entry or a draft with fewer content words matches almost anything
LOCK_WAIT, LOCK_STALE = 5.0, 10.0
RUNTIMES = {"node", "python", "go", "rust"}      # a language alone is no shared stack: every project in it would match


def _items(name):
    try:
        with open(os.path.join(coach.STATE, name), encoding="utf-8") as f: d = json.load(f)
        items = d.get("items") if isinstance(d, dict) else None
        return [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def _save(name, items):
    coach.write_json(os.path.join(coach.STATE, name), {"items": items})


@contextlib.contextmanager
def _lock():
    """One writer of the library files at a time, across tabs: each change reads, edits and writes them whole, and two at once
    would lose one (a Forget undone, a promotion lost). A lock older than LOCK_STALE was left by a process that died."""
    os.makedirs(coach.STATE, exist_ok=True)
    p = os.path.join(coach.STATE, "library.lock"); end = time.time() + LOCK_WAIT
    while True:
        try:
            os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)); break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(p) > LOCK_STALE: os.remove(p); continue
            except OSError: continue
            if time.time() > end: raise OSError("library is busy")
            time.sleep(0.05)
    try: yield
    finally:
        try: os.remove(p)
        except OSError: pass


def _worth(text):
    t = text.strip()
    return t[:1] not in ("/", "!", "#") and coach.scorable(t) and len(coach.body(t).split()) >= LIBRARY_MIN_WORDS


def candidate(text, project, now=None):
    """A prompt whose turn ended normally: kept pending until your next prompts say whether it worked."""
    if not _worth(text): return False
    t, now = coach.redact(text.strip()), time.time() if now is None else now
    with _lock():
        vetoes = [v for v in _items(VETOES) if now - v.get("ts", 0) < PENDING_DAYS * 86400]
        hit = next((v for v in vetoes if v.get("text") == t), None)
        if hit:                                      # corrected before its turn even ended: never a candidate
            vetoes.remove(hit); _save(VETOES, vetoes); return False
        items = _items(PENDING)[-(PENDING_MAX - 1):]
        items.append({"text": t, "project": project or "", "ts": now, "clean": 0})
        _save(PENDING, items)
    return True


def followup(text, prev=None, project=None, now=None):
    """Your next prompt, in `project`: a correction drops the prompt it answers (prev: the pane's reports can arrive out of order;
    without it nothing is dropped, as the newest candidate may be another tab's); otherwise each candidate of the same project gets
    one clean follow-up (another tab's prompts say nothing about it), and those with CLEAN_FOLLOWUPS are saved."""
    with _lock():
        items = _items(PENDING)
        if coach.is_correction(text):
            answered = coach.redact(prev.strip()) if prev else None
            if not answered: return
            if not any(c.get("text") == answered for c in items):     # its turn has not ended yet: veto it for when it does
                vetoes = _items(VETOES)[-(PENDING_MAX - 1):]
                _save(VETOES, vetoes + [{"text": answered, "ts": time.time() if now is None else now}]); return
            items = [c for c in items if c.get("text") != answered]
        else:
            for c in items:
                if project is None or c.get("project") == project: c["clean"] = c.get("clean", 0) + 1
        if items or _items(PENDING): _settle(items, lambda c: c.get("clean", 0) >= CLEAN_FOLLOWUPS, now)


def promote_due(now=None):
    """A candidate a day old with no correction has worked: save it (run by the session-start sweep)."""
    cut = (time.time() if now is None else now) - PENDING_DAYS * 86400
    with _lock():
        items = _items(PENDING)
        if items: _settle(items, lambda c: c.get("ts", 0) < cut, now)


def _settle(items, done, now):
    keep = [c for c in items if not done(c)]
    ready = [c for c in items if done(c)]
    if ready:
        lib = _items(LIB)
        for c in ready: lib = _add(lib, c, now)
        _save(LIB, _cap(lib, {_id(c) for c in ready}))
    _save(PENDING, keep)


def _id(c):
    """One id per prompt per project: the same prompt saved in two projects is two entries, forgotten separately."""
    return hashlib.sha1((c.get("project", "") + "\0" + c["text"]).encode("utf-8")).hexdigest()[:12]


def _add(lib, c, now):
    i = _id(c)
    old = next((e for e in lib if e.get("id") == i), None)
    if old: old["ts"] = time.time() if now is None else now; return lib
    stack = sorted({s.split("@")[0] for s in stackinfo.detect(c["project"])} - RUNTIMES) if c["project"] else []
    return lib + [{"id": i, "text": c["text"], "project": c["project"], "stack": stack, "ts": c.get("ts", 0), "uses": 0,
                   "off": coach.llm_off(c["project"])}]


def _cap(lib, new=()):
    """Per project, then in all: the least used go first, the oldest among equals; a prompt saved just now always stays, or a full
    library of used prompts would never take another."""
    def rank(e): return (e.get("id") in new, e.get("uses", 0), e.get("ts", 0))
    out = []
    for p in {e.get("project", "") for e in lib}:
        out += sorted((e for e in lib if e.get("project", "") == p), key=rank, reverse=True)[:CAP_PROJECT]
    return sorted(out, key=rank, reverse=True)[:CAP_GLOBAL]


STOP = set("""the and for with that this from into onto then than when what which who whom whose where while would could should
can will shall may might must have has had are was were been being does did not but all any each also just only very some
such its our your their them they you she him her his hers mine ours yours please there here how why about over under""".split())


def words(text):
    """Content words: lowercased, 3+ letters, the common ones dropped."""
    return {w for w in re.findall(r"[a-z][a-z0-9_]{2,}", coach.body(text).lower()) if w not in STOP}


def match(draft, project):
    """The saved prompt most like this draft (Jaccard over content words, MATCH or more), this project's first; another project's
    only when it shares a framework with this one and is not in llm-off.txt. Most used wins a tie. None when nothing is close."""
    w = words(draft)
    if not w: return None
    mine = set(sorted({s.split("@")[0] for s in stackinfo.detect(project)} - RUNTIMES)) if project else set()
    if len(w) < MIN_CONTENT: return None
    same = coach.redact(draft.strip())
    private, found = {}, []                          # llm-off.txt as it is now: a project added there later is private from then on
    for e in entries():
        p = e.get("project", "")
        if p != project and (e.get("off") or private.setdefault(p, coach.llm_off(p)) or not mine & set(e.get("stack", []))): continue
        if e.get("text") == same: continue           # the saved prompt itself (just put in the box by Use): nothing new to say
        ew = words(e.get("text", ""))
        if len(ew) < MIN_CONTENT: continue
        j = len(w & ew) / len(w | ew)
        if j >= MATCH: found.append((j, p == project, e.get("uses", 0), e))
    if not found: return None
    best = max(found, key=lambda f: f[:3])[3]        # closest, then this project's, then the most used
    return {"id": best["id"], "text": best["text"]}


def entries(project=None):
    """Saved prompts, most used first; this project's only when one is given."""
    lib = [e for e in _items(LIB) if project is None or e.get("project") == project]
    return sorted(lib, key=lambda e: (e.get("uses", 0), e.get("ts", 0)), reverse=True)


def _edit(i, change):
    with _lock():
        lib = _items(LIB); found = False
        for e in lib:
            if e.get("id") == i: found = True; change(lib, e); break
        if found: _save(LIB, lib)
    return found


def used(i):
    return _edit(i, lambda lib, e: e.update(uses=e.get("uses", 0) + 1))


def forget(i):
    return _edit(i, lambda lib, e: lib.remove(e))
