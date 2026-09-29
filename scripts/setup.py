"""Install or remove the coachline statusLine entry in settings.json.

  python setup.py              install (refuses to replace a statusline that is not ours)
  python setup.py --force      replace whatever statusline is set (old one is printed first)
  python setup.py --uninstall  remove our entry only
  python setup.py --advisor on|off      task-aware suggestions in the statusline and panel (background Claude calls)
  python setup.py --discover on|off     web search for better tools per kind of task (inside the advisor; verified locally)
  python setup.py --auto-open on|off    open the thread panel automatically when a session starts
  python setup.py --refresh    silent: if OUR entry points at another copy of this plugin
                               (e.g. an older version), re-point it here; otherwise do nothing.
                               The plugin's SessionStart hook runs this after updates.
"""
import json, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach

CONFIG = coach.CONFIG
SETTINGS = os.path.join(CONFIG, "settings.json")
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statusline.py")

def q(p):
    p = p.replace("\\", "/")  # forward slashes work in bash, cmd and PowerShell
    return f'"{p}"' if " " in p else p

def command():
    return f"{q(sys.executable)} {q(SCRIPT)}"

def ours(sl):
    """True if this statusLine runs a coachline script: a sibling coach.py exists, or the path says coachline
    (an old plugin version's folder may already be gone)."""
    script = coach.script_of(sl.get("command", "")) if isinstance(sl, dict) else None
    return bool(script) and (os.path.isfile(os.path.join(os.path.dirname(script), "coach.py")) or "coachline" in script.lower())

def entry(cur):
    """A fresh statusLine entry that keeps the user's refreshInterval (set by --auto-rewrite on)."""
    e = {"type": "command", "command": command()}
    if isinstance(cur, dict) and "refreshInterval" in cur: e["refreshInterval"] = cur["refreshInterval"]
    return e

def write(s):
    if os.path.exists(SETTINGS): shutil.copyfile(SETTINGS, SETTINGS + ".coach-bak")
    os.makedirs(CONFIG, exist_ok=True)
    with open(SETTINGS, "w", encoding="utf-8") as f: json.dump(s, f, indent=2)

KNOWN = {"--force", "--uninstall", "--refresh", "--advisor", "--auto-rewrite", "--auto-open", "--discover"}


def main(argv):
    if "-h" in argv or "--help" in argv: print(__doc__); return
    bad = [a for a in argv if a.startswith("-") and a not in KNOWN]
    if bad: sys.exit(f"unknown option {bad[0]}; nothing was changed (see --help)")
    try:
        with open(SETTINGS, encoding="utf-8") as f: s = json.load(f)
    except FileNotFoundError:
        s = {}
    except ValueError:
        if "--refresh" in argv: return  # never fail a session start over this
        sys.exit(f"{SETTINGS} is not valid JSON; fix it first (nothing was changed)")
    cur = s.get("statusLine")
    flag = next((f for f in ("--auto-open", "--advisor", "--auto-rewrite", "--discover") if f in argv), None)
    if flag:
        k = argv.index(flag); v = argv[k + 1] if k + 1 < len(argv) else ""
        if v not in ("on", "off"): sys.exit(f"usage: setup.py {flag} on|off")
        if flag == "--discover":
            coach.set_setting("discover", v == "on")
            print("Discovery ON (it runs inside the advisor, so keep --advisor on): once per kind of task, Claude searches the web for "
                  "better tools/skills/plugins and every suggestion is verified here before it is shown. Only a generic description of "
                  "the kind of task is used in searches, never your prompt. Nothing is installed. Turn off: setup.py --discover off"
                  if v == "on" else "Discovery OFF.")
            return
        if flag == "--auto-open":
            coach.set_setting("auto_open_watch", v == "on")
            print("Auto-open ON: a session start opens the thread panel in a new pane/window (never a second one while one is open). "
                  "Turn off: setup.py --auto-open off" if v == "on" else "Auto-open OFF.")
            return
        coach.set_setting("auto_rewrite", v == "on")  # --auto-rewrite is the old name of --advisor
        if ours(cur):  # refresh on a timer so a finished answer appears without waiting for the next message
            if v == "on": cur["refreshInterval"] = 10
            else: cur.pop("refreshInterval", None)
            write(s)
        print("Advisor ON: each prompt that looks like a task is redacted and sent, in the background, to `claude -p` (Haiku, your "
              "subscription) together with names of your installed skills and available plugins. Projects in llm-off.txt are never sent. "
              "Turn off: setup.py --advisor off" if v == "on" else "Advisor OFF.")
        return
    if "--refresh" in argv:
        if ours(cur) and coach.script_of(cur["command"]) != SCRIPT.replace("\\", "/"):
            s["statusLine"] = entry(cur); write(s)
        return
    if "--uninstall" in argv:
        if not ours(cur): print("no coachline statusLine set; nothing to do"); return
        del s["statusLine"]
    else:
        if cur and not ours(cur) and "--force" not in argv:
            sys.exit(f"a different statusLine is already set:\n  {cur}\nRe-run with --force to replace it.")
        s["statusLine"] = entry(cur)
    write(s)
    print("removed coachline statusLine" if "--uninstall" in argv else f"statusLine set: {s['statusLine']['command']}")

if __name__ == "__main__":
    main(sys.argv[1:])
