"""discover.py - the research pass: better tools, modern approaches, official docs and reference sites for the task you started.

Claude (your own subscription via `claude -p`, model `coach.model_for("research")`; its only tools are WebSearch and WebFetch)
gets a generic topic, your stack (framework names and major versions, from stackinfo.py) and the names of your installed skills,
never your prompt. Nothing it says is trusted: every suggestion is verified HERE
  - https URL on a public host (no localhost / private IPs; redirects are checked too),
  - the URL answers HTTP 200 and the page mentions the name,
  - a GitHub repo must exist (the API returns real stars and last push); archived or ~18-month-stale repos are dropped,
  - something made only for an older major version than your stack uses is dropped,
  - anything you already have is dropped.
Unverifiable suggestions are dropped. Nothing is ever installed. Text is stripped of terminal escapes before display.
It runs once per new task (cached per topic and stack for 7 days); a usage limit pauses it until the reset time.
  python discover.py --last        run it now for your last prompt (ignores the cache and any pause)
"""
import argparse, datetime as dt, ipaddress, json, os, re, socket, sys, time, urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach
from review import parse_json

TTL, MAX_ITEMS, MAX_RAW, STALE_DAYS, PAUSE = 7 * 86400, 4, 8, 550, 3600
KINDS = {"tool", "tech", "docs", "inspo"}       # anything else (skill, plugin, mcp, library, workflow, from older answers) is a tool
LIMIT = re.compile(r"usage limit|rate limit|limit reached|hit your limit|too many requests|\b429\b|\blimit\b.{0,60}\breset", re.I)
STOP = set("the and for with your that this from into make have using want need over under about more less very".split())


# ---------------------------------------------------------------- safe fetching
def public_https(url):
    try: u = urllib.parse.urlsplit(url)
    except ValueError: return False
    if u.scheme != "https" or not u.hostname or u.username or u.port not in (None, 443): return False
    h = u.hostname.lower()
    if h == "localhost" or h.endswith((".local", ".internal", ".localhost", ".lan")): return False
    try: return ipaddress.ip_address(h).is_global
    except ValueError: return "." in h


class _PublicOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not public_https(newurl): raise urllib.error.URLError("redirect to a non-public url")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _resolves_public(host):
    try: return all(ipaddress.ip_address(a[4][0]).is_global for a in socket.getaddrinfo(host, 443))
    except (OSError, ValueError): return False


def http_get(url, limit=300_000, timeout=8):
    """(status, text). status 0 = unreachable. COACHLINE_FETCH_STUB (a JSON file url -> {status, text}) replaces the network in tests."""
    stub = os.environ.get("COACHLINE_FETCH_STUB")
    if stub:
        with open(stub, encoding="utf-8") as f: d = json.load(f).get(url)
        return (d["status"], d.get("text", "")) if d else (404, "")
    if not public_https(url) or not _resolves_public(urllib.parse.urlsplit(url).hostname): return 0, ""
    req = urllib.request.Request(url, headers={"User-Agent": "coachline-verify (read-only check)", "Accept": "text/html,application/json"})
    try:
        with urllib.request.build_opener(_PublicOnly).open(req, timeout=timeout) as r: return r.status, r.read(limit).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e: return e.code, ""
    except (urllib.error.URLError, OSError, ValueError): return 0, ""


def github_repo(url):
    u = urllib.parse.urlsplit(url)
    parts = [p for p in u.path.split("/") if p]
    if (u.hostname or "").lower() not in ("github.com", "www.github.com") or len(parts) < 2 or parts[0] in ("orgs", "topics", "marketplace", "sponsors"):
        return None
    return parts[0], re.sub(r"\.git$", "", parts[1])


def _tokens(s): return [t for t in re.findall(r"[a-z0-9]{3,}", s.lower()) if t not in STOP]


def older_major(item, stack):
    """True when the item's NAME names a framework of the stack only at majors older than the project's ('Next.js 13' on next@15).
    Only whole version numbers right after the framework's own name count: not 'eslint-plugin-react 7', 'react 3d' or the 'why'."""
    text = coach.clean(item.get("name", "")).lower()
    for s in stack:
        name, _, major = s.rpartition("@")
        if not name or not major.isdigit(): continue
        base = re.escape(name[1:].split("/")[0] if name.startswith("@") else name.split("/")[-1].split(".")[0])   # @angular/core -> angular
        seen = [int(m) for m in re.findall(r"(?<![a-z0-9/@.-])" + base + r"(?:\.?js)?\s*v?(\d+)(?![a-z0-9.])", text)]
        if seen and max(seen) < int(major): return True
    return False


# ---------------------------------------------------------------- verification
def verify_item(item, have, get=http_get, now=None, stack=()):
    """(clean item, None) or (None, reason). Never trusts the model's claims."""
    if not isinstance(item, dict): return None, "not an object"
    name, url = coach.clean(item.get("name", ""))[:60], str(item.get("url", "")).strip()
    if not name or not public_https(url): return None, f"'{name}': no usable https url"
    if name.lower() in have: return None, f"'{name}': you already have it"
    kind = item.get("kind") if item.get("kind") in KINDS else "tool"
    if older_major(item, stack): return None, f"'{name}': made for an older version than this project uses"
    toks = _tokens(name)
    out = {"name": name, "kind": kind, "why": coach.clean(item.get("why", ""))[:140], "url": url,
           "install": coach.clean(item.get("install", "")).lstrip("$ ")[:120] if kind == "tool" else "", "stars": None, "pushed": None}
    gh = github_repo(url)
    if gh:
        st, txt = get(f"https://api.github.com/repos/{gh[0]}/{gh[1]}")
        if st == 404: return None, f"'{name}': github repo {gh[0]}/{gh[1]} does not exist"
        if st == 200:
            try: d = json.loads(txt)
            except ValueError: d = {}
            if d.get("archived"): return None, f"'{name}': repo is archived"
            pushed = str(d.get("pushed_at", ""))[:10]
            try:
                age = ((now or time.time()) - dt.datetime.strptime(pushed, "%Y-%m-%d").timestamp()) / 86400
            except ValueError:
                age = 0
            if age > STALE_DAYS: return None, f"'{name}': no push for {int(age)} days"
            if toks and not any(t in (str(d.get("full_name", "")) + " " + str(d.get("description") or "")).lower() for t in toks):
                return None, f"'{name}': does not match repo {d.get('full_name')}"
            out.update(stars=d.get("stargazers_count"), pushed=pushed or None); return out, None
    st, txt = get(url)   # not GitHub, or the GitHub API was unavailable (rate limit): fall back to the page itself
    if st != 200: return None, f"'{name}': url not reachable (HTTP {st})"
    if toks and not any(t in txt.lower() for t in toks): return None, f"'{name}': page does not mention it"
    return out, None


def verify_all(raw, have, get=http_get, stack=(), limit=MAX_ITEMS):
    ok, dropped = [], []
    for it in (raw if isinstance(raw, list) else [])[:MAX_RAW]:
        v, why = verify_item(it, have, get, stack=stack)
        if v and v["url"] not in [o["url"] for o in ok]: ok.append(v)
        elif why: dropped.append(why)
    return ok[:limit], dropped


# ---------------------------------------------------------------- asking Claude
def topic_key(advice, stack=()):
    """The same task on the same stack is researched once a week, across sessions and projects."""
    words = sorted({w for w in _tokens(advice.get("topic") or advice.get("summary", "")) if len(w) >= 3})[:6]
    return advice.get("task", "other") + ":" + " ".join(words) + "|" + ",".join(sorted(stack))


PROMPT = """You research for a developer who is about to give a task to Claude Code (a coding agent).
Task (generic; this is all you know about it): "{task}: {topic}".
Project stack, from its manifest files: {stack}.
Already installed in their Claude Code (do not recommend these or near-duplicates): {have}.
Use WebSearch, and WebFetch to confirm, to find up to 4 CURRENT things that would make the result clearly better. Mix kinds when it helps:
 - "tool": a Claude Code skill or plugin, an MCP server, a CLI or a library
 - "tech": a modern approach, API or framework feature to use instead of the obvious one
 - "docs": official documentation, a design guideline or a spec to follow (for example WCAG, Apple HIG, the framework's own docs)
 - "inspo": a real, live site or gallery that shows what a great result looks like
Prefer things maintained or updated in the last 12 months. Match the stack's major versions: never suggest something made for an
older major version, or a deprecated API. Search generic terms only. Every item needs the url of its official page, one you actually
saw in results or opened; do not guess urls.
Return ONLY a JSON object, no prose, no code fence:
{{"items":[{{"name":"official name","kind":"tool|tech|docs|inspo","why":"at most 20 words: what it makes better for THIS task","url":"https://...","install":"exact install command for a tool, else empty"}}]}}
Empty list if nothing is clearly better than a plain Claude Code session."""


def find(advice, stack=(), have=None, timeout=240):
    have = sorted(have_names() if have is None else have)
    text = coach.ask_claude(PROMPT.format(task=advice.get("task", "other"), topic=advice.get("topic") or advice.get("summary", ""),
                                          stack=", ".join(stack) or "unknown",
                                          have=", ".join(have[:80]) or "nothing"),
                            model=coach.model_for("research"), timeout=timeout, web=True)
    if LIMIT.search(text) and "{" not in text: raise RuntimeError(text[:300])     # a limit notice printed as the answer
    return parse_json(text).get("items", [])


def have_names():
    import advisor
    inst, _avail = advisor.catalog()
    return {n.lower() for i in inst for n in (i["name"], i["name"].split(":")[-1])}


def _load(name):
    try:
        with open(os.path.join(coach.STATE, name), encoding="utf-8") as f: d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _dump(name, d):
    """Write whole or not at all: another research or analysis job may be reading it."""
    os.makedirs(coach.STATE, exist_ok=True)
    tmp = os.path.join(coach.STATE, f"{name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f)
    for i in range(5):                            # Windows refuses to replace a file another process is reading: wait a moment
        try:
            os.replace(tmp, os.path.join(coach.STATE, name)); return
        except PermissionError:
            if i == 4:
                try: os.remove(tmp)
                except OSError: pass
                raise
            time.sleep(0.05 * (i + 1))


def pause_until(err, now=None):
    """When the subscription says no (a usage limit): the epoch time research may try again. The reset time Claude names
    ('...|1759420800' or 'resets 2pm' / 'resets at 14:00'), else an hour from now."""
    now = time.time() if now is None else now
    m = re.search(r"\|(\d{10})\b", err)
    if m and float(m.group(1)) > now: return float(m.group(1))
    m = re.search(r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", err, re.I)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if ap == "pm" and h < 12: h += 12
        if ap == "am" and h == 12: h = 0
        if h < 24 and mi < 60:
            t = dt.datetime.fromtimestamp(now).replace(hour=h, minute=mi, second=0, microsecond=0)
            if t.timestamp() <= now: t += dt.timedelta(days=1)
            return t.timestamp()
    return now + PAUSE


def paused_until(now=None):
    """'HH:MM' while a usage limit pauses research, else None."""
    t = _load("research-state.json").get("paused_until", 0)
    now = time.time() if now is None else now
    return dt.datetime.fromtimestamp(t).strftime("%H:%M") if isinstance(t, (int, float)) and t > now else None


def for_advice(advice, stack=(), fresh=False, get=http_get):
    """Up to MAX_RAW verified items for this task on this stack (memory.pick chooses what to show). Cached per topic and stack for 7 days. Never raises: research is a bonus.
    A usage limit pauses research; fresh (a run the user asked for) ignores the cache and the pause."""
    try:
        if not fresh and paused_until(): return []
        key, cache = topic_key(advice, stack), _load("discover-cache.json")
        hit = cache.get(key)
        if hit and not fresh and time.time() - hit.get("ts", 0) < TTL: return hit.get("items", [])
        try: raw = find(advice, stack)
        except RuntimeError as e:
            if LIMIT.search(str(e)):
                st = _load("research-state.json"); st["paused_until"] = pause_until(str(e)); _dump("research-state.json", st)
            return []
        items, _dropped = verify_all(raw, have_names() | {u["name"].lower() for u in advice.get("use", [])}, get, stack, limit=MAX_RAW)
        cache = {k: v for k, v in cache.items() if isinstance(v, dict) and time.time() - v.get("ts", 0) < TTL}
        cache[key] = {"ts": time.time(), "items": items}
        try: _dump("discover-cache.json", cache)
        except OSError: pass                      # the results still count; only the cache missed them
        return items
    except (RuntimeError, ValueError, OSError, KeyError, TypeError, AttributeError):
        return []


LOCK_STALE = 600


def wanted(session, advice):
    """Research this prompt? When it starts a new task, or when this session has had no research yet and none is under way."""
    if advice.get("new_task") is not False: return True
    st = _load("research-state.json")
    return session not in (st.get("done") or {}) and time.time() - (st.get("pending") or {}).get(session, 0) > 2 * LOCK_STALE


def _mark(session, done=False, pending=False):
    """Record a session as researched (done) or as waiting for research (pending); neither clears both."""
    st, now = _load("research-state.json"), time.time()
    for k in ("done", "pending"):
        st[k] = {s: t for s, t in (st.get(k) or {}).items() if isinstance(t, (int, float)) and now - t < TTL and s != session}
    if done: st["done"][session] = now
    if pending: st["pending"][session] = now
    _dump("research-state.json", st)


def _lock():
    """A token when this job may research (the lock file holds it), else None."""
    p = os.path.join(coach.STATE, "research.running")
    try:
        if time.time() - os.path.getmtime(p) > LOCK_STALE: os.remove(p)      # a crashed job never blocks research for good
    except OSError:
        pass
    tok = f"{os.getpid()}-{time.time()}"
    try:
        os.makedirs(coach.STATE, exist_ok=True)
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.write(fd, tok.encode()); os.close(fd)
        return tok
    except OSError:
        return None


def _unlock(tok):
    """Remove the lock only if it is still ours (it may have been taken over as stale)."""
    p = os.path.join(coach.STATE, "research.running")
    try:
        with open(p, encoding="utf-8") as f: mine = f.read() == tok
        if mine: os.remove(p)
    except OSError:
        pass


def _research(w, save):
    import memory
    items = memory.pick(for_advice(w["advice"], w.get("stack") or (), fresh=bool(w.get("fresh"))), key=w["key"])
    if items: save(w["key"], w["advice"], items)
    # a usage limit: the session is not researched, and its next prompt tries again
    _mark(w.get("session", ""), done=not paused_until())


def request(key, session, advice, stack, save, fresh=False):
    """Research for this prompt, newest request first. If another job is researching, leave the request for it and return: it
    takes the newest waiting request when it finishes, so an older one that never started is dropped. One web call at a time.
    save(key, advice, items) records a result (coach._save_discovery appends it to rewrites.jsonl). fresh (asked for by hand)
    ignores the cache and a usage-limit pause. Never raises."""
    try: _request(key, session, advice, stack, save, fresh)
    except (OSError, ValueError, KeyError, TypeError, AttributeError): pass


def _request(key, session, advice, stack, save, fresh=False):
    _mark(session, pending=True)                   # its follow-ups wait for this research instead of asking again
    _dump("research-want.json", {"key": key, "session": session, "advice": advice, "stack": list(stack), "fresh": bool(fresh), "ts": time.time()})
    done, p = None, os.path.join(coach.STATE, "research.running")
    while True:
        tok = _lock()
        if not tok: return
        try:
            while True:
                w = _load("research-want.json")
                if not w.get("key") or w["key"] == done: break
                try: os.utime(p)                   # a long drain is not a crashed job
                except OSError: pass
                done = w["key"]; _research(w, save)
        finally:
            _unlock(tok)
        w = _load("research-want.json")                # a request written just before the unlock must not be lost
        if not w.get("key") or w["key"] == done: return


# ---------------------------------------------------------------- display
def _stars(n):
    return "" if not isinstance(n, int) else f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def lines(items, width=96):
    """[(kind, text)] for the panel. Says plainly that these are web-found and unverified beyond the checks."""
    import textwrap
    if not items: return []
    out = [("dim", "web-found, not installed; only the checks above were verified. read before installing:")]
    for it in items:
        out += [("better", w) for w in textwrap.wrap(f"better: {it['name']} ({it['kind']}) - {it['why']}", width, subsequent_indent="        ")]
        meta = " · ".join(x for x in (f"{_stars(it['stars'])} stars" if it.get("stars") is not None else "", f"pushed {it['pushed']}" if it.get("pushed") else "") if x)
        out.append(("src", "  " + (meta + " · " if meta else "") + it["url"]))
        if it.get("install"): out.append(("src", "  install: " + it["install"]))
    return out


def compact(items):
    return [f"better: {it['name']} ({it['kind']}){' ' + _stars(it['stars']) + ' stars' if it.get('stars') is not None else ''} - {it['why']}  {it['url']}"[:200]
            for it in items[:2]]


def _advice_for(key):
    """The newest advice recorded for this prompt, or None."""
    adv = None
    try:
        with open(coach.REWRITES, encoding="utf-8") as f:
            for l in f:
                try: d = json.loads(l)
                except ValueError: continue
                if d.get("key") == key and d.get("advice"): adv = d["advice"]
    except OSError:
        pass
    return adv


def main(argv):
    ap = argparse.ArgumentParser(prog="discover.py", description="Search the web for better tools, approaches, docs and reference sites "
                                 "for a prompt's task. Sends a generic topic and your stack to a web search through your Claude subscription.")
    ap.add_argument("--last", action="store_true", help="do it now for your last prompt and print the result")
    ap.add_argument("--key", help="do it now, in the background, for one analysed prompt (the panel's r key)")
    a = ap.parse_args(argv)
    if not (a.last or a.key):
        ap.print_help(); return 2
    import advisor, memory, stackinfo
    if a.key:
        rows = coach.load_full(coach.HIST)
        row = next((r for r in rows if coach.prompt_key(r) == a.key), None)
        if row is None: sys.exit("no prompt with that key")
        if coach.llm_off(row[1]): sys.exit("this project is in llm-off.txt: not sending it anywhere")
        adv = _advice_for(a.key)
        if not adv: sys.exit("not analysed yet: analyse the prompt first")
        request(a.key, row[3], adv, stackinfo.detect(row[1]), coach._save_discovery, fresh=True)
        return 0
    rows = coach.load(coach.HIST); i, fails = coach.last_eval(rows)
    if i is None: sys.exit("no prompt to look at; run `coach.py --doctor`")
    if coach.llm_off(rows[i][1]): sys.exit("this project is in llm-off.txt: not sending it anywhere")
    adv = _advice_for(coach.prompt_key(rows[i]))
    try: adv = adv or advisor.advise(coach.redact(rows[i][2]), fails)
    except (RuntimeError, ValueError) as e: sys.exit(f"advice failed: {e}")
    print(f"kind of task: {adv['task']} - {adv.get('topic') or adv['summary']}\nsearching the web (up to ~4 min)...")
    items = memory.pick(for_advice(adv, stackinfo.detect(rows[i][1]), fresh=True))
    if not items: print("nothing verifiable found (suggestions that fail the checks are dropped)."); return 0
    for _k, t in lines(items, 100): print(t)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
