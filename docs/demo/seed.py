"""seed.py - the made-up world the README GIFs are recorded in, written to $CLAUDE_CONFIG_DIR (a temp dir, see setup.sh).

One conversation in a shoe-shop project, Claude's analysis of each prompt, web finds, patterns from earlier chats and a drafted
skill. Nothing here is real data, and nothing is sent anywhere.

  python3 docs/demo/seed.py              write the world
  python3 docs/demo/seed.py --fresh      the same earlier chats, but the conversation has no prompts yet
  python3 docs/demo/seed.py --send TEXT  add TEXT to the conversation, as Claude Code does when you send a prompt
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
import coach  # noqa: E402  (reads CLAUDE_CONFIG_DIR when imported)

SESSION, PROJECT = "demo-thread", "/Users/you/shoe-shop"
NOW = time.time()

THREAD = [
    (34, "add a size picker to the product page", {
        "task": "frontend", "summary": "size selection on the product page",
        "tips": ["Say where the sizes come from: the product API or a fixed list.", "Name the states: sold out, low stock, selected."],
        "use": [{"name": "frontend-design", "why": "consistent picker styling"}],
        "after": "Add a size picker to the product page (src/app/product/[id]/page.tsx).\n\nSizes come from the product API's `variants`. "
                 "Show sold-out sizes disabled and mark low stock (under 3).\n\nDone when: choosing a size updates the price and the Add to cart "
                 "button, and the existing product page tests pass."}),
    (22, "fix the login bug, users can't sign in", {
        "task": "debugging", "summary": "a login failure with no details",
        "tips": ["Paste the error and the steps that trigger it.", "Name the file or route, e.g. src/auth/login.ts.",
                 "Say what fixed means: a test that fails now and passes after."],
        "use": [{"name": "systematic-debugging", "why": "find the cause before changing code"}],
        "after": "Fix the login bug: [ASK: what happens, e.g. the error or status code] when [ASK: the steps that trigger it].\n\n"
                 "Find the cause in [ASK: the file or route, e.g. src/auth/login.ts] before changing anything, then write a test "
                 "that fails now.\n\nDone when: that test passes and the existing auth tests still pass."}),
    (11, "make the shoe site look more premium", {
        "task": "ui-design", "summary": "a premium look for a shoe store",
        "tips": ["Name the pages you want: home, catalog, product, cart.", "Give two or three reference sites you like.",
                 "Say what must not change: the checkout flow."],
        "use": [{"name": "frontend-design", "why": "a distinctive, polished look"}],
        "after": "Give the shoe store a premium, minimal look on the home, catalog, product and cart pages.\n\n"
                 "Use large product photography, generous whitespace, one serif display face for headings and a neutral palette "
                 "with a single accent. Keep the checkout flow and every URL unchanged.\n\nDone when: all four pages follow the "
                 "same type scale and spacing, and Lighthouse accessibility stays at 100."},
     [{"name": "Radix Colors", "kind": "tech", "why": "accessible neutral palettes with one accent, light and dark",
       "url": "https://www.radix-ui.com/colors", "install": "npm i @radix-ui/colors", "stars": 1900, "pushed": "2026-09"},
      {"name": "Refactoring UI", "kind": "inspo", "why": "spacing, type scale and colour choices that read as premium",
       "url": "https://www.refactoringui.com", "install": "", "stars": None, "pushed": None}]),
    (4, "commit this and open a pr with a good description", {
        "task": "git", "summary": "commit and pull request",
        "tips": ["Say which changes belong in this commit.", "Name the base branch and any reviewers."], "use": [],
        "after": "Commit the size picker changes only (not the styling work) with a conventional commit message, push the branch and "
                 "open a PR against main.\n\nThe PR description says what changed, why, and how it was tested."}),
]

# earlier chats: what the history review (learned.json) is drawn from
PAST = ["commit and open a pr for the cart fix", "fix the bug in checkout", "open a pr with these changes",
        "commit and open a pr, describe the refactor", "fix the bug where the search is empty", "commit this and open a pr",
        "please open a pr for the new footer"]

# what the stand-in for `claude -p` answers for a prompt sent while recording (fake_claude.py): the advice for the login bug
LIVE_ADVICE = dict(THREAD[1][2], topic="login bug", new_task=True, workflow=["Reproduce", "Find the cause", "Test", "Fix"])


def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: f.write(text)


def line(ts, text, sid):
    return json.dumps({"display": text, "timestamp": str(int(ts * 1000)), "project": PROJECT, "sessionId": sid}) + "\n"


def world(fresh=False):
    """fresh: earlier chats only, and an empty conversation you have just started."""
    hist = [line(NOW - 86400 * (9 - i), t, f"past-{i}") for i, t in enumerate(PAST)]
    recs = []
    for mins, text, advice, *web in ([] if fresh else THREAD):
        ts = NOW - mins * 60
        hist.append(line(ts, text, SESSION))
        rec = {"key": coach.prompt_key((float(int(ts * 1000)) / 1000, PROJECT, text)), "text": "AFTER: " + advice["after"], "advice": advice}
        if web: rec["discovery"] = web[0]
        recs.append(json.dumps(rec) + "\n")
    put(coach.HIST, "".join(hist))
    put(coach.REWRITES, "".join(recs))
    put(coach.USER_CFG, json.dumps({"panel_ai": True, "research": False, "auto_open": False}))
    put(coach.LEARNED, json.dumps({"generated": time.strftime("%Y-%m-%d"), "prompts": len(PAST) + len(THREAD),
        "requests": [{"name": "commit-and-open-pr", "keywords": ["open a pr"], "count": 6}],
        "mistakes": [{"name": "bug-without-details", "keywords": ["fix the"], "fix": "Paste the error and the steps that trigger it."}]}))
    put(os.path.join(coach.STATE, "drafts", "commit-and-open-pr", "SKILL.md"),
        "---\nname: commit-and-open-pr\ndescription: Commit the current changes and open a pull request with a clear description.\n---\n")
    for name in ("frontend-design", "systematic-debugging"):
        put(os.path.join(coach.CONFIG, "skills", name, "SKILL.md"), f"---\nname: {name}\ndescription: demo skill\n---\n")
    put(os.path.join(coach.CONFIG, "demo-advice.json"), json.dumps(LIVE_ADVICE))


if __name__ == "__main__":
    if sys.argv[1:2] == ["--send"]:
        with open(coach.HIST, "a", encoding="utf-8") as f: f.write(line(time.time(), " ".join(sys.argv[2:]), SESSION))
    else:
        world(fresh=sys.argv[1:2] == ["--fresh"])
