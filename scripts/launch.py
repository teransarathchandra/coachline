"""launch.py - open the panel as a SPLIT PANE next to Claude Code, once. Opt-in: setup.py --auto-open on

  python launch.py --auto       hook mode (SessionStart): silent; does nothing unless auto-open is on
  python launch.py              split a pane now
  python launch.py --dry-run    print the command it would run
  python launch.py --command    print the command that opens the panel by hand (works in any terminal)

Only real splits are used: tmux, or Windows Terminal. No separate windows. In any other terminal nothing opens by
itself; run the --command line in a second tab or pane. It never opens a second panel: watch.py keeps a heartbeat.
"""
import os, platform, shlex, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach

WATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watch.py")
LOCK = os.path.join(coach.STATE, "watch.launching")


def plan(system, env, py, watch, which=shutil.which, extra=()):
    """argv that splits a pane running the panel, or None when this terminal cannot split. Pure: no I/O."""
    cmd = [py, watch, *extra]
    if system != "Windows" and env.get("TMUX") and which("tmux"):          # split the current tmux window, keep focus on Claude
        a = ["tmux", "split-window", "-h", "-d", "-l", "45%"]
        if env.get("CLAUDE_CONFIG_DIR"): a += ["-e", "CLAUDE_CONFIG_DIR=" + env["CLAUDE_CONFIG_DIR"]]
        return a + [" ".join(shlex.quote(c) for c in cmd)]
    if system == "Windows" and env.get("WT_SESSION") and which("wt.exe"):  # inside Windows Terminal: split this window, focus back on Claude
        return ["wt.exe", "-w", "0", "split-pane", "-V", "--size", "0.45", *cmd, ";", "move-focus", "left"]
    return None


def ensure_shim():
    """A launcher at a path that never changes (~/.claude/coach/panel.py); it forwards to this version's watch.py."""
    p = os.path.join(coach.STATE, "panel.py")
    body = ("# coachline: opens the panel. Rewritten automatically after plugin updates; safe to delete.\n"
            f"import runpy, sys\nsys.argv[0] = {WATCH!r}\nrunpy.run_path({WATCH!r}, run_name=\"__main__\")\n")
    try:
        try:
            with open(p, encoding="utf-8") as f: same = f.read() == body
        except OSError: same = False
        if not same:
            os.makedirs(coach.STATE, exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as f: f.write(body)
    except OSError:
        pass
    return p


def panel_command():
    """The short, permanent command that opens the panel by hand."""
    p = ensure_shim().replace("\\", "/")
    exe = sys.executable; name = None
    for n in ("python", "python3"):
        w = shutil.which(n)
        try:
            if w and os.path.samefile(w, exe): name = n; break
        except OSError: pass
    return f"{name or (chr(34) + exe + chr(34) if ' ' in exe else exe)} " + (f'"{p}"' if " " in p else p)


def spawn(argv):
    kw = {"creationflags": 0x08000000} if os.name == "nt" else {"start_new_session": True}   # wt.exe / tmux: no window of their own
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)


KNOWN = {"--auto", "--dry-run", "--command", "--watch-args"}


def main(argv, system=None, env=None, opener=spawn, which=shutil.which):
    if "-h" in argv or "--help" in argv: print(__doc__); return 0
    mine = argv[:argv.index("--watch-args")] if "--watch-args" in argv else argv
    if [a for a in mine if a not in KNOWN]: print("unknown option; nothing was opened (see --help)"); return 2
    if "--command" in argv: print(panel_command()); return 0
    auto, dry = "--auto" in argv, "--dry-run" in argv
    extra = tuple(argv[argv.index("--watch-args") + 1:]) if "--watch-args" in argv else ()
    ensure_shim()
    if auto and not coach.setting("auto_open_watch", False): return 0
    if coach.panel_alive():
        if not auto: print("the panel is already open")
        return 0
    if not dry and os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < 10: return 0  # another session is opening it
    a = plan(system or platform.system(), env if env is not None else os.environ, sys.executable, WATCH, which=which, extra=extra)
    if dry: print(a); return 0
    if a is None:
        if not auto: print("this terminal cannot split a pane (only tmux and Windows Terminal can). Open a second tab or pane and run:\n  " + panel_command())
        return 0 if auto else 1
    os.makedirs(coach.STATE, exist_ok=True)
    with open(LOCK, "w") as f: f.write(str(time.time()))
    try: opener(a)
    except OSError as e:
        if not auto: print(f"could not split a pane: {e}")
        return 0 if auto else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
