import json, os, tempfile, time, unittest

from test_review import run, write_history, read

FLAGGED = "please handle this carefully and make it work for every customer in the system"
AFTER = json.dumps({"task": "frontend", "summary": "polishing a page", "use": [], "get": [], "tips": ["Name the style: modern and polished."],
                    "workflow": ["Sketch it", "Build it"], "after": "Fix the parser and verify with the test suite."})


class AutoSuggestions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.cfg = self.tmp.name
        write_history(self.cfg, [FLAGGED])
        self.log = os.path.join(self.cfg, "sent.log"); self.state = os.path.join(self.cfg, "coach")
        self.cache = os.path.join(self.state, "last-rewrite.json")

    def tearDown(self): self.tmp.cleanup()

    def calls(self):
        return read(self.log).count("=====") if os.path.exists(self.log) else 0

    def wait_cache(self, status, seconds=20):
        end = time.time() + seconds
        while time.time() < end:
            if os.path.exists(self.cache):
                try:
                    if json.loads(read(self.cache)).get("status") == status: return
                except ValueError: pass  # mid-write
            time.sleep(0.2)
        self.fail(f"cache never reached {status!r}")

    def test_fixes_show_by_default_with_no_llm_call(self):
        out = run(self.cfg, "statusline.py", FAKE_JSON=AFTER).stdout
        self.assertIn("- no-vague:", out)
        self.assertNotIn("AFTER", out)
        self.assertEqual(self.calls(), 0)

    def test_auto_rewrite_runs_once_in_the_background_and_shows_up(self):
        self.assertEqual(run(self.cfg, "setup.py").returncode, 0)
        r = run(self.cfg, "setup.py", "--auto-rewrite", "on"); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(read(os.path.join(self.cfg, "settings.json")))["statusLine"]["refreshInterval"], 10)
        first = run(self.cfg, "statusline.py", FAKE_JSON=AFTER).stdout
        self.assertIn("working on it", first)
        self.wait_cache("done")
        with open(os.path.join(self.state, "rewrites.jsonl"), encoding="utf-8") as f:  # watch.py reads this log
            logged = [json.loads(l) for l in f]
        self.assertEqual(len(logged), 1)
        self.assertIn("Fix the parser", logged[0]["text"])
        shown =run(self.cfg, "statusline.py", FAKE_JSON=AFTER).stdout
        self.assertIn("AFTER: Fix the parser and verify with the test suite.", shown)
        self.assertIn("task: frontend", shown)
        self.assertIn("tip: Name the style: modern and polished.", shown)
        run(self.cfg, "statusline.py", FAKE_JSON=AFTER)
        self.assertEqual(self.calls(), 1, "one Claude call per prompt, however many refreshes")
        run(self.cfg, "setup.py", "--auto-rewrite", "off")
        self.assertNotIn("refreshInterval", json.loads(read(os.path.join(self.cfg, "settings.json")))["statusLine"])
        self.assertNotIn("AFTER", run(self.cfg, "statusline.py", FAKE_JSON=AFTER).stdout)

    def test_llm_off_project_is_never_sent_even_when_enabled(self):
        write_history(self.cfg, [FLAGGED + " again"], project="D:/work/employer-x")
        os.makedirs(self.state, exist_ok=True)
        with open(os.path.join(self.state, "llm-off.txt"), "w") as f: f.write("employer-x\n")
        run(self.cfg, "setup.py", "--auto-rewrite", "on")
        out = run(self.cfg, "statusline.py", FAKE_JSON=AFTER).stdout
        time.sleep(1)
        self.assertNotIn("AFTER", out)
        self.assertEqual(self.calls(), 0)

    def test_failure_is_shown_once_and_not_retried_in_a_loop(self):
        run(self.cfg, "setup.py", "--auto-rewrite", "on")
        run(self.cfg, "statusline.py", FAKE_MODE="fail")
        self.wait_cache("failed")
        out = run(self.cfg, "statusline.py", FAKE_MODE="fail").stdout
        self.assertIn("advice: (unavailable", out)
        run(self.cfg, "statusline.py", FAKE_MODE="fail")
        self.assertEqual(self.calls(), 1)

    def test_update_refresh_keeps_the_refresh_interval(self):
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"statusLine": {"type": "command", "refreshInterval": 10,
                                      "command": "python /gone/plugins/cache/coachline/coachline/0.2.0/scripts/statusline.py"}}, f)
        run(self.cfg, "setup.py", "--refresh")
        s = json.loads(read(os.path.join(self.cfg, "settings.json")))["statusLine"]
        self.assertEqual(s["refreshInterval"], 10)
        self.assertNotIn("/gone/", s["command"])


if __name__ == "__main__":
    unittest.main()
