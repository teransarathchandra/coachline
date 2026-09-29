import json, os, tempfile, unittest

from test_review import run, write_history, read

HISTORY = ["make my shoe store website look modern and polished for every customer please"]
ADVICE = json.dumps({"task": "ui-design", "summary": "polishing a shoe store website", "use": [], "get": [], "tips": [], "workflow": [], "after": "Polish it."})
WEB = json.dumps({"items": [{"name": "GreatKit", "kind": "tool", "why": "does it better", "url": "https://tools.example.com/g", "install": "npm i greatkit"}]})


class NothingRunsByAccident(unittest.TestCase):
    """--help and unknown options must never act: no settings rewritten, no window opened, nothing sent to Claude."""

    def test_help_and_bad_options_have_no_side_effects(self):
        cases = [("discover.py", ["--help"], 0), ("discover.py", [], 2), ("discover.py", ["--bogus"], None),
                 ("setup.py", ["--help"], 0), ("setup.py", ["--bogus"], None), ("setup.py", ["-x"], None),
                 ("launch.py", ["--help"], 0), ("launch.py", ["--bogus"], 2)]
        for script, args, want in cases:
            with tempfile.TemporaryDirectory() as cfg:
                write_history(cfg, HISTORY)
                r = run(cfg, script, *args, FAKE_JSON=ADVICE, FAKE_JSON_WEB=WEB)
                label = f"{script} {args}"
                if want is None: self.assertNotEqual(r.returncode, 0, label)
                else: self.assertEqual(r.returncode, want, label + r.stderr)
                self.assertFalse(os.path.exists(os.path.join(cfg, "sent.log")), label + ": called Claude")
                self.assertFalse(os.path.exists(os.path.join(cfg, "settings.json")), label + ": wrote settings")
                self.assertFalse(os.path.exists(os.path.join(cfg, "coach", "watch.launching")), label + ": tried to open a panel")
                if want == 0: self.assertIn("usage" if script == "discover.py" else "python", (r.stdout + r.stderr).lower(), label)

    def test_discover_last_runs_end_to_end_and_shows_only_verified_items(self):
        with tempfile.TemporaryDirectory() as cfg:
            write_history(cfg, HISTORY)
            stub = os.path.join(cfg, "stub.json")
            with open(stub, "w") as f: json.dump({"https://tools.example.com/g": {"status": 200, "text": "GreatKit"}}, f)
            r = run(cfg, "discover.py", "--last", FAKE_JSON=ADVICE, FAKE_JSON_WEB=WEB, COACHLINE_FETCH_STUB=stub)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("kind of task: ui-design", r.stdout)
            self.assertIn("better: GreatKit (tool)", r.stdout)
            self.assertIn("web-found, not installed", r.stdout)
            self.assertEqual(read(os.path.join(cfg, "sent.log")).count("=====") , 2)   # one advisor call, one web call

    def test_discover_last_respects_the_opt_out_list(self):
        with tempfile.TemporaryDirectory() as cfg:
            with open(os.path.join(cfg, "history.jsonl"), "w") as f:
                f.write(json.dumps({"display": HISTORY[0], "timestamp": "1750000000000", "project": "D:/work/employer-x", "sessionId": "s"}) + "\n")
            os.makedirs(os.path.join(cfg, "coach"))
            with open(os.path.join(cfg, "coach", "llm-off.txt"), "w") as f: f.write("employer-x\n")
            r = run(cfg, "discover.py", "--last", FAKE_JSON=ADVICE, FAKE_JSON_WEB=WEB)
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(cfg, "sent.log")))


if __name__ == "__main__":
    unittest.main()
