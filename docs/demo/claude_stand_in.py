"""claude_stand_in.py - a bare stand-in for the Claude Code prompt, the left pane of the README GIFs (see setup.sh).

It only does what the GIFs need: /plugin marketplace add and /plugin install remember that coachline is installed, /exit quits,
and a started session with coachline installed opens the real panel (scripts/watch.py) in a tmux split, as the session-start hook
does. A prompt is added to the demo history, where the panel picks it up; no model is called from here.
"""
import itertools, json, os, subprocess, sys, time

CFG = os.environ["CLAUDE_CONFIG_DIR"]
DEMO = os.path.dirname(os.path.abspath(__file__))
INSTALLED = os.path.join(CFG, "demo-installed")
ORANGE, DIM, BOLD, GREEN, RESET = "\033[38;5;173m", "\033[90m", "\033[1m", "\033[32m", "\033[0m"


def rule():
    cols = os.get_terminal_size().columns if sys.stdout.isatty() else 60
    print(DIM + "─" * cols + RESET)


def start():
    print("\033[2J\033[H" + f"\n {ORANGE}✻{RESET} {BOLD}Claude Code{RESET}\n   {DIM}~/shoe-shop{RESET}\n")
    if os.path.exists(INSTALLED):
        os.makedirs(os.path.join(CFG, "coach"), exist_ok=True)
        with open(os.path.join(CFG, "coach", "current-session.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "demo-thread", "ts": time.time()}, f)
        subprocess.run(["tmux", "split-window", "-h", "-d", "-l", "58%", f"python3 {os.path.join(DEMO, '..', '..', 'scripts', 'watch.py')}"])


def reply(text):
    print(f" {DIM}⎿{RESET}  {text}\n")


def working():
    for ch in itertools.cycle("✻✶✳✢·✢✳✶"):
        print(f"\r {ORANGE}{ch} Working…{RESET}", end="", flush=True)
        time.sleep(0.15)


def main():
    start()
    while True:
        rule()
        try: text = input(f"{BOLD}>{RESET} ").strip()
        except EOFError: return
        rule()
        if not text: continue
        print(f"\n{DIM}>{RESET} {text}")
        if text == "/exit": return
        if text.startswith("/plugin marketplace add"): reply(f"{GREEN}✓{RESET} Added marketplace coachline")
        elif text.startswith("/plugin install"):
            open(INSTALLED, "w").close()
            reply(f"{GREEN}✓{RESET} Installed coachline. Restart Claude Code to load it.")
        else:
            subprocess.run([sys.executable, os.path.join(DEMO, "seed.py"), "--send", text])
            print(); working()


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: pass
