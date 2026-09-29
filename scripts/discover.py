"""discover.py - web discovery: better tools, skills, plugins or workflows for the kind of task you are doing.

Claude (your own subscription via `claude -p`; its only tools are WebSearch and WebFetch) searches the web for
things that do this job better than what you have. Nothing it says is trusted: every suggestion is verified HERE
  - https URL on a public host (no localhost / private IPs; redirects are checked too),
  - the URL answers HTTP 200 and the page mentions the name,
  - a GitHub repo must exist (the API returns real stars and last push); archived or ~18-month-stale repos are dropped,
  - anything you already have is dropped.
Unverifiable suggestions are dropped. Nothing is ever installed. Text is stripped of terminal escapes before display.
It runs once per kind of task (cached 24h). Opt in with: setup.py --discover on
  python discover.py --last        run it now for your last prompt's kind of task (ignores the cache)
"""
import argparse, datetime as dt, ipaddress, json, os, re, socket, sys, time, urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach
from review import parse_json

TTL, MAX_ITEMS, STALE_DAYS = 24 * 3600, 3, 550
KINDS = {"skill", "plugin", "mcp", "tool", "library", "workflow"}
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


# ---------------------------------------------------------------- verification
def verify_item(item, have, get=http_get, now=None):
    """(clean item, None) or (None, reason). Never trusts the model's claims."""
    if not isinstance(item, dict): return None, "not an object"
    name, url = coach.clean(item.get("name", ""))[:60], str(item.get("url", "")).strip()
    if not name or not public_https(url): return None, f"'{name}': no usable https url"
    if name.lower() in have: return None, f"'{name}': you already have it"
    toks = _tokens(name)
    out = {"name": name, "kind": item.get("kind") if item.get("kind") in KINDS else "tool", "why": coach.clean(item.get("why", ""))[:140],
           "url": url, "install": coach.clean(item.get("install", "")).lstrip("$ ")[:120], "stars": None, "pushed": None}
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


def verify_all(raw, have, get=http_get):
    ok, dropped = [], []
    for it in (raw if isinstance(raw, list) else [])[:6]:
        v, why = verify_item(it, have, get)
        if v and v["url"] not in [o["url"] for o in ok]: ok.append(v)
        elif why: dropped.append(why)
    return ok[:MAX_ITEMS], dropped


# ---------------------------------------------------------------- asking Claude
def topic_key(advice):
    words = sorted({w for w in _tokens(advice.get("summary", "")) if len(w) >= 4})[:3]
    return advice.get("task", "other") + ":" + " ".join(words)


PROMPT = """You help a developer find BETTER tools for a kind of task. Kind of task (generic; this is all you know): "{task}: {summary}".
Use WebSearch, and WebFetch to confirm, to find up to 3 currently maintained things that could do this job better than a plain
Claude Code session: Claude Code skills or plugins, MCP servers, CLI tools, libraries, or proven workflows. Search generic terms only.
Only report a url you actually saw in the results or opened; do not guess urls.
Return ONLY a JSON object, no prose, no code fence:
{{"items":[{{"name":"official name","kind":"skill|plugin|mcp|tool|library|workflow","why":"at most 20 words: why it does this job better","url":"https://...","install":"exact install command, or empty"}}]}}
Empty list if nothing clearly better exists."""


def find(advice, timeout=150):
    text = coach.ask_claude(PROMPT.format(task=advice.get("task", "other"), summary=advice.get("summary", "")), timeout=timeout, web=True)
    return parse_json(text).get("items", [])


def have_names():
    import advisor
    inst, _avail = advisor.catalog()
    return {n.lower() for i in inst for n in (i["name"], i["name"].split(":")[-1])}


def _cache():
    try:
        with open(os.path.join(coach.STATE, "discover-cache.json"), encoding="utf-8") as f: d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def for_advice(advice, fresh=False, get=http_get):
    """Verified items for this kind of task. Cached per topic for 24h. Never raises: discovery is a bonus."""
    try:
        key, cache = topic_key(advice), _cache()
        hit = cache.get(key)
        if hit and not fresh and time.time() - hit.get("ts", 0) < TTL: return hit.get("items", [])
        items, _dropped = verify_all(find(advice), have_names() | {u["name"].lower() for u in advice.get("use", [])}, get)
        cache = {k: v for k, v in cache.items() if time.time() - v.get("ts", 0) < 7 * 86400}
        cache[key] = {"ts": time.time(), "items": items}
        os.makedirs(coach.STATE, exist_ok=True)
        with open(os.path.join(coach.STATE, "discover-cache.json"), "w", encoding="utf-8") as f: json.dump(cache, f)
        return items
    except (RuntimeError, ValueError, OSError, KeyError):
        return []


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


def main(argv):
    ap = argparse.ArgumentParser(prog="discover.py", description="Search the web for better tools for your last prompt's kind of task. "
                                 "Sends a generic task description to a web search through your Claude subscription.")
    ap.add_argument("--last", action="store_true", help="do it now (nothing runs without this flag)")
    if not ap.parse_args(argv).last:
        ap.print_help(); return 2
    import advisor
    rows = coach.load(coach.HIST); i, fails = coach.last_eval(rows)
    if i is None: sys.exit("no prompt to look at; run `coach.py --doctor`")
    if coach.llm_off(rows[i][1]): sys.exit("this project is in llm-off.txt: not sending it anywhere")
    key = coach.prompt_key(rows[i]); adv = None
    try:
        with open(coach.REWRITES, encoding="utf-8") as f:
            for l in f:
                try: d = json.loads(l)
                except ValueError: continue
                if d.get("key") == key and d.get("advice"): adv = d["advice"]
    except OSError:
        pass
    try: adv = adv or advisor.advise(coach.redact(rows[i][2]), fails)
    except (RuntimeError, ValueError) as e: sys.exit(f"advice failed: {e}")
    print(f"kind of task: {adv['task']} - {adv['summary']}\nsearching the web (up to ~2 min)...")
    items = for_advice(adv, fresh=True)
    if not items: print("nothing verifiable found (suggestions that fail the checks are dropped)."); return 0
    for _k, t in lines(items, 100): print(t)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
