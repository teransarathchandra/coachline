"""launch.py - open the watch panel next to Claude Code, once. Opt-in: setup.py --auto-open on

  python launch.py --auto       hook mode (SessionStart): silent; does nothing unless auto-open is on
  python launch.py              open a panel now
  python launch.py --dry-run    print the command it would run
It never opens a second panel: watch.py keeps a heartbeat file, and a recent one means "already open".
"""
import os, platform, shlex, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach

WATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watch.py")
LOCK = os.path.join(coach.STATE, "watch.launching")


def plan(system, env, py, watch, which=shutil.which, extra=()):
    """argv that opens the panel in a new pane/window for this platform, or None. Pure: no I/O."""
    cmd = [py, watch, *extra]
    if system != "Windows" and env.get("TMUX") and which("tmux"):  # split the current tmux window, keep focus on Claude
        a = ["tmux", "split-window", "-h", "-d", "-l", "45%"]
        if env.get("CLAUDE_CONFIG_DIR"): a += ["-e", "CLAUDE_CONFIG_DIR=" + env["CLAUDE_CONFIG_DIR"]]
        return a + [" ".join(shlex.quote(c) for c in cmd)]
    if system == "Windows":
        if env.get("WT_SESSION") and which("wt.exe"):            # inside Windows Terminal: split this window, focus back on Claude
            return ["wt.exe", "-w", "0", "split-pane", "-V", "--size", "0.45", *cmd, ";", "move-focus", "left"]
        return cmd                                               # anywhere else: spawn() gives it its own console window
    if system == "Darwin":
        inner = " ".join(shlex.quote(c) for c in cmd).replace("\\", "\\\\").replace('"', '\\"')
        return ["osascript", "-e", f'tell application "Terminal" to do script "{inner}"']
    if env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"):
        for term, flag in (("gnome-terminal", "--"), ("konsole", "-e"), ("xfce4-terminal", "-x"), ("kitty", ""),
                           ("alacritty", "-e"), ("xterm", "-e"), ("x-terminal-emulator", "-e")):
            if which(term): return [term] + ([flag] if flag else []) + cmd
    return None


def spawn(argv):
    if os.name == "nt":  # `cmd /c start` did not start anything when launched from a hook-like context; Python asks for the console itself
        kw = {"creationflags": 0x08000000 if os.path.basename(argv[0]).lower().startswith("wt") else 0x00000010}  # NO_WINDOW for wt, else NEW_CONSOLE
    else:
        kw = {"start_new_session": True}
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)


KNOWN = {"--auto", "--dry-run", "--watch-args"}


def main(argv, system=None, env=None, opener=spawn):
    if "-h" in argv or "--help" in argv: print(__doc__); return 0
    mine = argv[:argv.index("--watch-args")] if "--watch-args" in argv else argv
    if [a for a in mine if a not in KNOWN]: print("unknown option; nothing was opened (see --help)"); return 2
    auto, dry = "--auto" in argv, "--dry-run" in argv
    extra = tuple(argv[argv.index("--watch-args") + 1:]) if "--watch-args" in argv else ()
    if auto and not coach.setting("auto_open_watch", False): return 0
    if coach.panel_alive():
        if not auto: print("the panel is already open")
        return 0
    if not dry and os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < 10: return 0  # another session is opening it
    a = plan(system or platform.system(), env if env is not None else os.environ, sys.executable, WATCH, extra=extra)
    if dry: print(a); return 0
    if a is None:
        if not auto: print("no terminal launcher found here; open a second pane and run: " + " ".join([sys.executable, WATCH]))
        return 0 if auto else 1
    os.makedirs(coach.STATE, exist_ok=True)
    with open(LOCK, "w") as f: f.write(str(time.time()))
    try: opener(a)
    except OSError as e:
        if not auto: print(f"could not open a terminal: {e}")
        return 0 if auto else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
