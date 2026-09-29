"""Install or remove the coachline statusLine entry in settings.json.

  python setup.py              install (refuses to replace a statusline that is not ours)
  python setup.py --force      replace whatever statusline is set (old one is printed first)
  python setup.py --uninstall  remove our entry only
Re-run after a plugin update: the plugin folder path can change per version.
"""
import json, os, shutil, sys

CONFIG = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
SETTINGS = os.path.join(CONFIG, "settings.json")
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statusline.py")

def q(p):
    p = p.replace("\\", "/")  # forward slashes work in bash, cmd and PowerShell
    return f'"{p}"' if " " in p else p

def command():
    return f"{q(sys.executable)} {q(SCRIPT)}"

def ours(sl):
    return isinstance(sl, dict) and "statusline.py" in sl.get("command", "") and "coach" in sl.get("command", "").lower()

def main(argv):
    try:
        with open(SETTINGS, encoding="utf-8") as f: s = json.load(f)
    except FileNotFoundError:
        s = {}
    except ValueError:
        sys.exit(f"{SETTINGS} is not valid JSON; fix it first (nothing was changed)")
    cur = s.get("statusLine")
    if "--uninstall" in argv:
        if not ours(cur): print("no coachline statusLine set; nothing to do"); return
        del s["statusLine"]
    else:
        if cur and not ours(cur) and "--force" not in argv:
            sys.exit(f"a different statusLine is already set:\n  {cur}\nRe-run with --force to replace it.")
        s["statusLine"] = {"type": "command", "command": command()}
    if os.path.exists(SETTINGS): shutil.copyfile(SETTINGS, SETTINGS + ".coach-bak")
    os.makedirs(CONFIG, exist_ok=True)
    with open(SETTINGS, "w", encoding="utf-8") as f: json.dump(s, f, indent=2)
    print("removed coachline statusLine" if "--uninstall" in argv else f"statusLine set: {s['statusLine']['command']}")

if __name__ == "__main__":
    main(sys.argv[1:])
