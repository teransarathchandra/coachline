import json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach  # noqa: E402


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

    def test_macos_and_linux_turn_analysis_and_the_pane_on_by_default(self):
        for system in ("Darwin", "Linux"):
            with self.on(system):
                self.assertTrue(coach.ai_on(), system)
                self.assertTrue(coach.auto_open_on(), system)

    def test_windows_keeps_both_opt_in(self):
        with self.on("Windows"):
            self.assertFalse(coach.ai_on())
            self.assertFalse(coach.auto_open_on())

    def test_a_value_the_user_wrote_always_wins(self):
        self.write(panel_ai=False, auto_open_watch=False)
        with self.on("Darwin"):
            self.assertFalse(coach.ai_on()); self.assertFalse(coach.auto_open_on())
        self.write(panel_ai=True, auto_open_watch=True)
        with self.on("Windows"):
            self.assertTrue(coach.ai_on()); self.assertTrue(coach.auto_open_on())

    def test_the_old_auto_rewrite_name_is_still_honoured(self):
        self.write(auto_rewrite=False)
        with self.on("Darwin"): self.assertFalse(coach.ai_on())
        self.write(auto_rewrite=True)
        with self.on("Windows"): self.assertTrue(coach.ai_on())

    def test_discover_stays_off_everywhere(self):
        for system in ("Darwin", "Linux", "Windows"):
            with self.on(system): self.assertFalse(coach.setting("discover", False))


if __name__ == "__main__":
    unittest.main()
