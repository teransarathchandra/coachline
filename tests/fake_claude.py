"""Stand-in for `claude -p` in tests: logs its arguments and stdin, answers from env.
FAKE_JSON answers normal calls; FAKE_JSON_WEB answers calls that were given the web tools."""
import os, sys
data = sys.stdin.read()
web = "WebSearch,WebFetch" in sys.argv
if os.environ.get("FAKE_LOG"):
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f: f.write("ARGS: " + " ".join(sys.argv[1:]) + "\n" + data + "\n=====\n")
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "fail": sys.stderr.write("boom"); sys.exit(1)
print("this is not json" if mode == "bad" else os.environ.get("FAKE_JSON_WEB" if web else "FAKE_JSON", "{}"))
