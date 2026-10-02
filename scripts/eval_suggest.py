"""eval_suggest.py - how good are the suggestions? Runs 10 fixed prompts through the engine LIVE, on your Claude subscription.

  python eval_suggest.py          show what it would send (nothing is sent)
  python eval_suggest.py --yes    run it: 10 fast calls and 10 web research calls, several minutes
The prompts are fixed examples, never your own. Reports per prompt and in total: latency, what the fast pass named, what research
found and kept, the kind mix, and the share of recommendations you do not already have. Saved to <state>/eval/<time>.json.
Run it before and after an engine change and compare. Not run in CI.
"""
import argparse, collections, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CASES = [
    ("ui-design", "make the landing page of my shoe store look premium and modern", ["node", "next@15", "react@19", "tailwindcss@4"]),
    ("frontend", "add a checkout page with address form validation and a payment step", ["node", "next@15", "react@19", "react-hook-form@7"]),
    ("backend", "build a REST endpoint that lists orders with pagination and filtering", ["python", "fastapi@0", "sqlalchemy@2"]),
    ("debugging", "the dashboard is slow to load, find out why and fix it", ["node", "react@18", "vite@5"]),
    ("testing", "write end to end tests for the signup and login flow", ["node", "next@15", "react@19"]),
    ("infra", "set up CI that runs the tests and deploys to production on every merge to main", ["node"]),
    ("data", "the monthly report query on postgres takes 40 seconds, make it fast", ["python", "django@5", "psycopg@3"]),
    ("docs", "write a README for this CLI so new users can install and use it", ["go@1.22"]),
    ("refactoring", "split this 800 line component into smaller pieces without changing behaviour", ["node", "vue@3", "pinia@2"]),
    ("ui-design", "make the settings screen accessible for keyboard and screen reader users", ["node", "react@19"]),
]


def summary(rows):
    use = sum(len(r.get("use", [])) for r in rows); get = sum(len(r.get("get", [])) for r in rows)
    ver = sum(len(r.get("verified", [])) for r in rows); raw = sum(r.get("raw", 0) for r in rows); rec = use + get + ver
    def avg(k):
        xs = [r[k] for r in rows if k in r]
        return round(sum(xs) / len(xs), 1) if xs else None
    return {"prompts": len(rows), "errors": sum(1 for r in rows if r.get("error")), "recommended": rec,
            "not_installed_share": round((get + ver) / rec, 2) if rec else None, "verified_rate": round(ver / raw, 2) if raw else None,
            "kinds": dict(collections.Counter(i["kind"] for r in rows for i in r.get("verified", []))),
            "fast_s_avg": avg("fast_s"), "research_s_avg": avg("research_s")}


def run_case(task, text, stack, have):
    import advisor, discover
    r = {"task": task, "prompt": text, "stack": stack}
    t0 = time.time()
    try: adv = advisor.advise(text, [])
    except (RuntimeError, ValueError) as e:
        r["error"] = f"fast: {e}"[:200]; return r
    r["fast_s"] = round(time.time() - t0, 1)
    r["use"], r["get"] = [u["name"] for u in adv["use"]], [g["name"] for g in adv["get"]]
    t1 = time.time()
    try: raw = discover.find(adv, stack)
    except (RuntimeError, ValueError) as e:
        r["error"] = f"research: {e}"[:200]; raw = []
    r["research_s"] = round(time.time() - t1, 1)
    ok, dropped = discover.verify_all(raw, have, stack=stack)
    r.update(raw=len(raw) if isinstance(raw, list) else 0, dropped=dropped, verified=[{"name": i["name"], "kind": i["kind"], "url": i["url"]} for i in ok])
    return r


def pct(x): return "-" if x is None else f"{x:.0%}"


def main(argv):
    ap = argparse.ArgumentParser(prog="eval_suggest.py", description="Measure the suggestion engine on 10 fixed prompts (live).")
    ap.add_argument("--yes", action="store_true", help="really send the 10 fixed prompts (nothing is sent without it)")
    if not ap.parse_args(argv).yes:
        print(__doc__); print(f"would send {len(CASES)} prompts:")
        for _t, text, _s in CASES: print("  -", text)
        return 2
    import coach, discover
    have = discover.have_names(); rows = []
    for task, text, stack in CASES:
        r = run_case(task, text, stack, have); rows.append(r)
        print(f"{task:<12} fast {r.get('fast_s', '-')}s  research {r.get('research_s', '-')}s  use {len(r.get('use', []))}  get {len(r.get('get', []))}  "
              f"web {len(r.get('verified', []))}/{r.get('raw', 0)}" + (f"  ERROR {r['error']}" if r.get("error") else ""), flush=True)
    s = summary(rows)
    print(f"\n{s['recommended']} recommended, not installed {pct(s['not_installed_share'])}, research verified {pct(s['verified_rate'])}, "
          f"kinds {s['kinds']}, avg fast {s['fast_s_avg']}s, avg research {s['research_s_avg']}s, errors {s['errors']}")
    out = os.path.join(coach.STATE, "eval", time.strftime("%Y%m%d-%H%M%S") + ".json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f: json.dump({"summary": s, "rows": rows}, f, indent=2)
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
