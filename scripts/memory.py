"""memory.py - what the research pass has already shown you, and what you did with it. Local only; never sent anywhere.

<state>/suggestions.json: {"items": {id: {"name", "kind", "url", "shown": [prompt keys], "status": "dismissed"|"adopted", "ts"}}}
An item is shown with at most MAX_SHOWN prompts; one you hid (x) or already use (a) is never suggested again.
"""
import time, urllib.parse

import discover

NAME, MAX_SHOWN, MAX_KEEP = "suggestions.json", 2, 500
STATUSES = ("dismissed", "adopted")


def item_id(item):
    """The same page is the same suggestion, however the model spelled its url."""
    u = urllib.parse.urlsplit(str(item.get("url", "")).strip().lower())
    host = u.hostname or ""
    if host.startswith("www."): host = host[4:]
    return (host + u.path.rstrip("/")) or str(item.get("name", "")).strip().lower()


def _items():
    d = discover._load(NAME).get("items")
    return {k: v for k, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}


def _save(its):
    if len(its) > MAX_KEEP:                       # forget the oldest unmarked ones; your choices are kept
        loose = sorted((k for k, v in its.items() if v.get("status") not in STATUSES), key=lambda k: its[k].get("ts", 0))
        for k in loose[:len(its) - MAX_KEEP]: its.pop(k)
    discover._dump(NAME, {"items": its})


def statuses():
    return {k: v["status"] for k, v in _items().items() if v.get("status") in STATUSES}


def pick(items, key=None, limit=discover.MAX_ITEMS):
    """Up to `limit` items worth showing: none you hid or use, none already shown with MAX_SHOWN other prompts.
    With `key` (the prompt they are shown with) the showing is recorded."""
    its, out = _items(), []
    for x in items:
        rec = its.get(item_id(x), {})
        if rec.get("status") in STATUSES: continue
        if len([k for k in rec.get("shown", []) if k != key]) >= MAX_SHOWN: continue
        out.append(x)
        if len(out) == limit: break
    if key and out:
        for x in out:
            rec = its.setdefault(item_id(x), {})
            rec.update(name=x.get("name", ""), kind=x.get("kind", "tool"), url=x.get("url", ""), ts=time.time())
            if key not in rec.setdefault("shown", []): rec["shown"].append(key)
        try: _save(its)
        except OSError: pass
    return out


def mark(iid, status):
    """Hide an item for good (dismissed) or note that you use it (adopted). False when nothing was saved."""
    if status not in STATUSES or not iid: return False
    its = _items(); its.setdefault(iid, {}).update(status=status, ts=time.time())
    try:
        _save(its); return True
    except OSError:
        return False
