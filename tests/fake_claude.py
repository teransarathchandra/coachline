"""Stand-in for `claude -p` in tests: logs stdin, answers from env."""
import os, sys
data = sys.stdin.read()
if os.environ.get("FAKE_LOG"):
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f: f.write(data + "\n=====\n")
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "fail": sys.stderr.write("boom"); sys.exit(1)
print("this is not json" if mode == "bad" else os.environ.get("FAKE_JSON", "{}"))
