import json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach  # noqa: E402
from test_review import run, read  # noqa: E402


class Defaults(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = coach.USER_CFG
        coach.USER_CFG = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        coach.USER_CFG = self.saved; self.tmp.cleanup()

    def on(self, system):
        return mock.patch.dict(os.environ, {"COACHLINE_PLATFORM": system})

    def write(self, **kw):
        with open(coach.USER_CFG, "w") as f: json.dump(kw, f)

    def test_analysis_is_on_everywhere_but_windows_auto_open_stays_opt_in(self):
        for system in ("Darwin", "Linux", "Windows"):
            with self.on(system): self.assertTrue(coach.ai_on(), system)
        with self.on("Darwin"): self.assertTrue(coach.auto_open_on())
        with self.on("Windows"): self.assertFalse(coach.auto_open_on())

    def test_a_value_the_user_wrote_always_wins(self):
        self.write(panel_ai=False, auto_open_watch=False)
        with self.on("Darwin"):
            self.assertFalse(coach.ai_on()); self.assertFalse(coach.auto_open_on())
        self.write(panel_ai=True, auto_open_watch=True)
        with self.on("Windows"):
            self.assertTrue(coach.ai_on()); self.assertTrue(coach.auto_open_on())

    def test_the_old_auto_rewrite_name_is_still_honoured(self):
        self.write(auto_rewrite=False)
        with self.on("Windows"): self.assertFalse(coach.ai_on())
        self.write(auto_rewrite=True)
        with self.on("Windows"): self.assertTrue(coach.ai_on())

    def test_research_follows_analysis_and_honours_the_old_discover_name(self):
        for system in ("Darwin", "Linux", "Windows"):
            with self.on(system): self.assertTrue(coach.research_on(), system)
        self.write(discover=False); self.assertFalse(coach.research_on())
        self.write(discover=False, research=True); self.assertTrue(coach.research_on())      # the new name wins
        self.write(research=True, panel_ai=False); self.assertFalse(coach.research_on())     # never without analysis

    def test_models_default_to_haiku_and_sonnet_and_ignore_unknown_names(self):
        self.assertEqual((coach.model_for("fast"), coach.model_for("research")), ("haiku", "sonnet"))
        self.write(model_fast="sonnet", model_research="gpt-9")
        self.assertEqual((coach.model_for("fast"), coach.model_for("research")), ("sonnet", "sonnet"))


class SetupSwitches(unittest.TestCase):
    def conf(self, cfg):
        return json.loads(read(os.path.join(cfg, "coach", "config.json")))

    def test_research_and_model_switches(self):
        with tempfile.TemporaryDirectory() as cfg:
            self.assertEqual(run(cfg, "setup.py", "--research", "off").returncode, 0)
            self.assertEqual(run(cfg, "setup.py", "--model", "research", "opus").returncode, 0)
            self.assertEqual((self.conf(cfg)["research"], self.conf(cfg)["model_research"]), (False, "opus"))
            self.assertEqual(run(cfg, "setup.py", "--discover", "on").returncode, 0)               # the old name
            self.assertTrue(self.conf(cfg)["research"])
            for bad in (["--model", "research", "gpt-9"], ["--model", "slow", "haiku"], ["--model"]):
                r = run(cfg, "setup.py", *bad)
                self.assertNotEqual(r.returncode, 0, bad); self.assertIn("usage", r.stderr)
            shown = run(cfg, "setup.py").stdout
            for want in ("web research per new task (--research):  ON", "research model:  opus", "fast model:  haiku"):
                self.assertIn(want, shown)


if __name__ == "__main__":
    unittest.main()
