import glob, json, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from test_review import run, read  # noqa: E402
from test_advisor import make_config  # noqa: E402
import eval_suggest  # noqa: E402

ADV = json.dumps({"task": "ui-design", "summary": "polish a store", "use": [{"name": "design-polish", "why": "fits"}], "get": [], "after": "x"})
WEB = json.dumps({"items": [{"name": "GreatKit", "kind": "tool", "why": "better", "url": "https://tools.example.com/g"},
                            {"name": "Ghost", "kind": "tool", "why": "invented", "url": "https://tools.example.com/none"}]})


class Eval(unittest.TestCase):
    def test_nothing_is_sent_without_yes(self):
        with tempfile.TemporaryDirectory() as cfg:
            r = run(cfg, "eval_suggest.py")
            self.assertEqual(r.returncode, 2)
            self.assertIn(f"would send {len(eval_suggest.CASES)} prompts", r.stdout)
            self.assertFalse(os.path.exists(os.path.join(cfg, "sent.log")))

    def test_it_runs_every_case_and_reports_the_share_you_do_not_have(self):
        with tempfile.TemporaryDirectory() as cfg:
            make_config(cfg)
            stub = os.path.join(cfg, "stub.json")
            with open(stub, "w") as f: json.dump({"https://tools.example.com/g": {"status": 200, "text": "GreatKit"}}, f)
            r = run(cfg, "eval_suggest.py", "--yes", FAKE_JSON=ADV, FAKE_JSON_WEB=WEB, COACHLINE_FETCH_STUB=stub)
            self.assertEqual(r.returncode, 0, r.stderr)
            s = json.loads(read(glob.glob(os.path.join(cfg, "coach", "eval", "*.json"))[0]))["summary"]
            self.assertEqual((s["prompts"], s["errors"], s["recommended"]), (10, 0, 20))   # 1 installed + 1 web-found per prompt
            self.assertEqual((s["not_installed_share"], s["verified_rate"], s["kinds"]), (0.5, 0.5, {"tool": 10}))
            self.assertIn("not installed 50%", r.stdout)

    def test_summary_survives_failed_cases(self):
        s = eval_suggest.summary([{"error": "fast: boom"}, {"use": [], "get": [], "verified": [], "raw": 0, "fast_s": 2.0}])
        self.assertEqual((s["prompts"], s["errors"], s["recommended"], s["not_installed_share"], s["verified_rate"]), (2, 1, 0, None, None))
        self.assertEqual(s["fast_s_avg"], 2.0)


if __name__ == "__main__":
    unittest.main()
