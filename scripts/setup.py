"""Settings for coachline. The panel is the interface; there is no statusline any more.

  python setup.py                       show the current settings and the command that opens the panel
  python setup.py --panel-ai on|off     Claude analyses your history and every prompt of this thread (background `claude -p`
                                        calls on your subscription; no API key; llm-off.txt projects are never sent)
  python setup.py --auto-open on|off    split a pane with the panel at session start (tmux or Windows Terminal only)
  python setup.py --discover on|off     web search for better tools per kind of task (inside the analysis; verified locally)
  python setup.py --uninstall           remove the old coachline statusline entry from settings.json
  python setup.py --refresh             silent: used by the SessionStart hook (refreshes the launcher, migrates the old statusline)
Old names still work: --advisor and --auto-rewrite mean --panel-ai.
"""
import json, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach
import launch

SETTINGS = os.path.join(coach.CONFIG, "settings.json")
KNOWN = {"--panel-ai", "--advisor", "--auto-rewrite", "--auto-open", "--discover", "--uninstall", "--refresh"}


def ours(sl):
    """True if this statusLine entry is the old coachline statusline (a sibling coach.py exists, or the path says coachline;
    an old plugin version's folder may already be gone)."""
    script = coach.script_of(sl.get("command", "")) if isinstance(sl, dict) else None
    return bool(script) and (os.path.isfile(os.path.join(os.path.dirname(script), "coach.py")) or "coachline" in script.lower())


def write(s):
    if os.path.exists(SETTINGS): shutil.copyfile(SETTINGS, SETTINGS + ".coach-bak")
    os.makedirs(coach.CONFIG, exist_ok=True)
    with open(SETTINGS, "w", encoding="utf-8") as f: json.dump(s, f, indent=2)


def onoff(argv, flag):
    k = argv.index(flag); v = argv[k + 1] if k + 1 < len(argv) else ""
    if v not in ("on", "off"): sys.exit(f"usage: setup.py {flag} on|off")
    return v == "on"


def main(argv):
    if "-h" in argv or "--help" in argv: print(__doc__); return
    bad = [a for a in argv if a.startswith("-") and a not in KNOWN]
    if bad: sys.exit(f"unknown option {bad[0]}; nothing was changed (see --help)")
    try:
        with open(SETTINGS, encoding="utf-8") as f: s = json.load(f)
    except FileNotFoundError:
        s = {}
    except ValueError:
        if "--refresh" in argv: return                  # never fail a session start over this
        sys.exit(f"{SETTINGS} is not valid JSON; fix it first (nothing was changed)")
    cur = s.get("statusLine")
    if "--refresh" in argv:
        launch.ensure_shim()
        if ours(cur): del s["statusLine"]; write(s)     # the panel replaced the statusline
        return
    if "--uninstall" in argv:
        if ours(cur): del s["statusLine"]; write(s); print("removed the old coachline statusLine entry")
        else: print("no coachline statusLine entry; nothing to do")
        return
    if "--panel-ai" in argv or "--advisor" in argv or "--auto-rewrite" in argv:
        on = onoff(argv, next(f for f in ("--panel-ai", "--advisor", "--auto-rewrite") if f in argv))
        coach.set_setting("panel_ai", on)
        print("Claude analysis ON. In the background, on your Claude subscription (no API key): (1) each prompt of the current thread is "
              "redacted and sent to `claude -p` (Haiku) with the names of your installed skills and plugins, to get improvements and an enhanced "
              "prompt; (2) every ~2 days Claude analyses your last 90 days of redacted prompts to find requests you repeat and mistakes you "
              "keep making. Projects in llm-off.txt are never sent. Turn off: setup.py --panel-ai off" if on else "Claude analysis OFF.")
        return
    if "--discover" in argv:
        on = onoff(argv, "--discover")
        coach.set_setting("discover", on)
        print("Discovery ON (it runs inside Claude analysis, so keep --panel-ai on): once per kind of task, Claude searches the web for "
              "better tools/skills/plugins and every suggestion is verified here before it is shown. Only a generic description of "
              "the kind of task is used in searches, never your prompt. Nothing is installed. Turn off: setup.py --discover off" if on else "Discovery OFF.")
        return
    if "--auto-open" in argv:
        on = onoff(argv, "--auto-open")
        coach.set_setting("auto_open_watch", on)
        print("Auto-open ON: a session start splits a pane with the panel (tmux or Windows Terminal; never a second one while one is open). "
              "Turn off: setup.py --auto-open off" if on else "Auto-open OFF.")
        return
    launch.ensure_shim()
    print(f"coachline settings ({coach.USER_CFG})")
    print(f"  Claude analysis (--panel-ai):  {'ON' if coach.ai_on() else 'off'}")
    print(f"  auto-open a split pane (--auto-open):  {'ON' if coach.setting('auto_open_watch', False) else 'off'}")
    print(f"  web discovery (--discover):  {'ON' if coach.setting('discover', False) else 'off'}")
    print(f"open the panel by hand, in a second tab or pane:\n  {launch.panel_command()}")


if __name__ == "__main__":
    main(sys.argv[1:])
