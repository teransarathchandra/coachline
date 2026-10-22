"""Settings for coachline. The panel is the interface; there is no statusline any more.

  python setup.py                       show the current settings and the command that opens the panel
  python setup.py --panel-ai on|off     Claude analyses your history and every prompt of this thread (background `claude -p`
                                        calls on your subscription; no API key; llm-off.txt projects are never sent)
  python setup.py --auto-open on|off    split a pane with the panel at session start (tmux or Windows Terminal only)
  python setup.py --research on|off     web research once per new task: tools, modern approaches, docs, reference sites (verified here)
  python setup.py --model fast|research haiku|sonnet|opus   the model of each pass (defaults: fast haiku, research sonnet)
  python setup.py --hints on|off       the hint under the prompt box as you type: its meter and what it lacks (on by default; local)
  python setup.py --level beginner|pro|auto   hint wording: beginners also get why (auto: beginner until 50 prompts in your history)
  python setup.py --hold on|off        hold a clearly vague prompt at Enter; a second Enter within 30 s sends it (off by default)
  python setup.py --motion on|off      the panel's animations (on by default; off by itself with NO_COLOR, over SSH, in a slow terminal)
  python setup.py --uninstall           remove the old coachline statusline entry from settings.json
  python setup.py --refresh             silent: used by the SessionStart hook (refreshes the launcher, records which session started, migrates the old statusline)
Old names still work: --advisor and --auto-rewrite mean --panel-ai, --discover means --research.
"""
import json, os, shutil, sys, threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach
import launch

SETTINGS = os.path.join(coach.CONFIG, "settings.json")
KNOWN = {"--panel-ai", "--advisor", "--auto-rewrite", "--auto-open", "--research", "--discover", "--model", "--motion", "--hints", "--hold", "--level", "--uninstall", "--refresh"}


def ours(sl):
    """True if this statusLine entry is the old coachline statusline (a sibling coach.py exists, or the path says coachline;
    an old plugin version's folder may already be gone)."""
    script = coach.script_of(sl.get("command", "")) if isinstance(sl, dict) else None
    return bool(script) and (os.path.isfile(os.path.join(os.path.dirname(script), "coach.py")) or "coachline" in script.lower())


def write(s):
    if os.path.exists(SETTINGS): shutil.copyfile(SETTINGS, SETTINGS + ".coach-bak")
    coach.write_json(SETTINGS, s, stamp=False, indent=2)       # Claude Code's own file: whole or not at all, and no "v" of ours


def onoff(argv, flag):
    k = argv.index(flag); v = argv[k + 1] if k + 1 < len(argv) else ""
    if v not in ("on", "off"): sys.exit(f"usage: setup.py {flag} on|off")
    return v == "on"


STUCK = []


def hook_json(wait=1.0):
    """What Claude Code pipes to a hook, or '' when there is nothing within `wait` seconds. A session start must never block on this."""
    if sys.stdin is None or sys.stdin.isatty(): return ""
    box = []

    def read():
        try: box.append(sys.stdin.read())
        except (OSError, ValueError): pass
    t = threading.Thread(target=read, daemon=True); t.start(); t.join(wait)
    if t.is_alive(): STUCK.append(t)                          # an open pipe nobody writes to: do not wait for it at exit either
    return box[0] if box else ""


def main(argv):
    if "-h" in argv or "--help" in argv: print(__doc__); return
    if "--refresh" in argv:
        coach.record_session(hook_json(), tab=coach.tab_key())      # the hook's JSON: which session just started
        try: coach.sweep()
        except OSError: pass                                         # housekeeping never fails a session start
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
              f"redacted and sent to `claude -p` ({coach.model_for('fast')}) with the names of your installed skills and plugins, to get improvements and an enhanced "
              "prompt; (2) every ~2 days Claude analyses your last 90 days of redacted prompts to find requests you repeat and mistakes you "
              "keep making. Projects in llm-off.txt are never sent. Turn off: setup.py --panel-ai off" if on else "Claude analysis OFF.")
        return
    if "--research" in argv or "--discover" in argv:
        on = onoff(argv, "--research" if "--research" in argv else "--discover")
        coach.set_setting("research", on)
        print("Research ON (part of Claude analysis): once per new task, Claude searches the web for better tools, modern approaches, "
              "official docs and reference sites, and every suggestion is verified here before it is shown. Searches get a generic "
              "task topic, your stack's framework names and versions, and your installed skill names, never your prompt. Nothing is "
              "installed. Turn off: setup.py --research off" if on else "Research OFF.")
        return
    if "--model" in argv:
        k = argv.index("--model"); which, name = (argv[k + 1:k + 3] + ["", ""])[:2]
        if which not in ("fast", "research") or name not in coach.MODELS:
            sys.exit("usage: setup.py --model fast|research haiku|sonnet|opus")
        coach.set_setting("model_" + which, name)
        print(f"The {which} pass now uses {name}.")
        return
    if "--level" in argv:
        k = argv.index("--level"); v = argv[k + 1] if k + 1 < len(argv) else ""
        if v not in ("beginner", "pro", "auto"): sys.exit("usage: setup.py --level beginner|pro|auto")
        coach.set_setting("level", v)
        print(f"Level {v}: " + {"beginner": "hints say why", "pro": "hints are terse",
                                 "auto": f"hints say why until your history holds {coach.BEGINNER_PROMPTS} prompts"}[v] + ".")
        return
    if "--hold" in argv:
        on = onoff(argv, "--hold")
        coach.set_setting("hold", on)
        print("Hold ON: a clearly vague prompt stops at Enter with what it lacks, and goes back in the box. Press Enter again within 30 s "
              "to send it as is. Turn off: setup.py --hold off" if on else "Hold OFF: Enter always sends.")
        return
    if "--hints" in argv:
        on = onoff(argv, "--hints")
        coach.set_setting("hints", on)
        print("Hints ON: while you type, the line under the prompt box shows how concrete the draft is and what it lacks. "
              "Worked out on this machine; the draft is never sent. Turn off: setup.py --hints off" if on else "Hints OFF.")
        return
    if "--motion" in argv:
        on = onoff(argv, "--motion")
        coach.set_setting("motion", on)
        print("Motion ON: the panel shimmers while Claude works, reveals a new analysis, flashes Copied and fills the meter. "
              "Off by itself with NO_COLOR, over SSH or in a slow terminal. Turn off: setup.py --motion off" if on else "Motion OFF: every frame is still.")
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
    print(f"  auto-open a split pane (--auto-open):  {'ON' if coach.auto_open_on() else 'off'}")
    print(f"  web research per new task (--research):  {'ON' if coach.research_on() else 'off'}")
    print(f"  hint wording (--level):  {coach.level()}" + ("" if coach.setting("level") in ("beginner", "pro") else " (auto)"))
    print(f"  hold a vague prompt at Enter (--hold):  {'ON' if coach.hold_on() else 'off'}")
    print(f"  hints under the prompt box (--hints):  {'ON' if coach.hints_on() else 'off'}")
    print(f"  motion (--motion):  {'ON' if coach.motion_on() else 'off'}")
    print(f"  fast model:  {coach.model_for('fast')}   research model:  {coach.model_for('research')}   (--model fast|research <name>)")
    print(f"open the panel by hand, in a second tab or pane:\n  {launch.panel_command()}")


if __name__ == "__main__":
    main(sys.argv[1:])
    if STUCK:
        sys.stdout.flush(); sys.stderr.flush(); os._exit(0)
