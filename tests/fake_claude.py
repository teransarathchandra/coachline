"""Stand-in for `claude -p` in tests: logs its arguments and stdin, answers from env.
FAKE_JSON answers normal calls; FAKE_JSON_WEB answers calls that were given the web tools."""
import os, sys
data = sys.stdin.read()
web = "WebSearch,WebFetch" in sys.argv
if os.environ.get("FAKE_LOG"):
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f: f.write("ARGS: " + " ".join(sys.argv[1:]) + "\n" + data + "\n=====\n")
if os.environ.get("FAKE_LOG") and os.environ.get("FAKE_LOCK"):   # lets a test see whether a lock was held during the call
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f: f.write("LOCK=" + str(os.path.exists(os.environ["FAKE_LOCK"])) + "\n")
bad_once = os.environ.get("FAKE_BAD_ONCE")      # path of a marker file: the first call answers badly, later calls normally
if bad_once and not os.path.exists(bad_once):
    open(bad_once, "w").close(); print("Sure! Here is my creative answer to your request, in prose."); sys.exit(0)
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "fail": print(os.environ.get("FAKE_STDOUT", "")); sys.stderr.write(os.environ.get("FAKE_ERR", "boom")); sys.exit(1)
print("this is not json" if mode == "bad" else os.environ.get("FAKE_JSON_WEB" if web else "FAKE_JSON", "{}"))
