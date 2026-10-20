"""Stand-in for `claude -p` while the GIFs are recorded: thinks for a moment, then answers with the demo advice seed.py wrote."""
import os, sys, time

sys.stdin.read()
time.sleep(float(os.environ.get("DEMO_THINK", "3")))
with open(os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "demo-advice.json"), encoding="utf-8") as f: print(f.read())
