import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach, gold  # noqa: E402


def read(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def run(script, cfg, *args):
    env = {**os.environ, "CLAUDE_CONFIG_DIR": cfg, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", script), *args],
                          capture_output=True, text=True, encoding="utf-8", env=env)


class Rules(unittest.TestCase):
    def test_each_rule_fires_and_passes(self):
        self.assertFalse(coach.r4_qualifiers("do this carefully"))
        self.assertTrue(coach.r4_qualifiers("do this and print the count"))
        self.assertFalse(coach.r3_evidence("x [Pasted text #1 +369 lines]"))
        self.assertTrue(coach.r3_evidence("[Pasted text #1 +9 lines]"))
        self.assertFalse(coach.r2_dont_touch("merge the branch"))
        self.assertTrue(coach.r2_dont_touch("merge it but do not force"))
        self.assertTrue(coach.r1_done_when("short one"))
        self.assertFalse(coach.r1_done_when("word " * 30))

    def test_rejection_needs_cue_gap_and_no_reason(self):
        self.assertFalse(coach.r5_rejection("still not working", 60))
        self.assertTrue(coach.r5_rejection("still broken because rule X", 60))
        self.assertTrue(coach.r5_rejection("still not working", 5000))
        self.assertTrue(coach.r5_rejection("Fine, go with X", 60))

    def test_verdict_does_not_praise_short_prompts(self):
        self.assertEqual(coach.verdict("provide a commit message", []), "short")
        self.assertEqual(coach.verdict("word " * 30, []), "5/5")
        self.assertEqual(coach.verdict("still broken", ["rejection-loop"]), "4/5")


class Redaction(unittest.TestCase):
    def test_secrets_are_removed(self):
        for raw, secret, tag in [("a.b@x.org", "a.b@x.org", "<email>"),
                                 ("d32a787f-85f4-4775-a39c-095516bda637", "d32a787f", "<guid>"),
                                 ("password=hunter2", "hunter2", "<secret>"),
                                 ("AccountKey=abcd1234==", "abcd1234", "<secret>"),
                                 ("Authorization: Bearer abcdefghijklmnopqrstuvwx", "abcdefghijklmnop", "<token>"),
                                 ("sk-abcdefghijklmnopqrstuv", "abcdefghijklmnop", "<key>")]:
            out = coach.redact("see " + raw + " ok")
            self.assertIn(tag, out, raw)
            self.assertNotIn(secret, out, raw)


class Loading(unittest.TestCase):
    def setUp(self):  # never read the real ~/.claude/coach/config.json
        self._cfg = coach.USER_CFG; coach.USER_CFG = os.path.join(tempfile.gettempdir(), "coachline-no-such-config.json")

    def tearDown(self):
        coach.USER_CFG = self._cfg

    def test_missing_and_malformed_history_do_not_crash(self):
        self.assertEqual(coach.load(os.path.join(tempfile.gettempdir(), "nope.jsonl")), [])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "h.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write('not json\n{"display": "hello there friend", "timestamp": 1000}\n{"x": 1}\n')
            self.assertEqual(len(coach.load(p)), 1)

    def test_repeat_window_finds_densest_burst(self):
        day = 86400
        hits = {"c": [(i * day, "x") for i in (0, 1, 2, 60)]}
        self.assertEqual(coach.clusters(hits)["c"][:2], (4, 3))
        self.assertEqual(coach.clusters({"c": [(0, "x"), (60 * day, "x")]}), {})

    def test_repeat_note_counts_the_last_14_days_only(self):
        day = 86400; msg = "write a commit message for this"
        rows = [(i * day, "p", msg) for i in (0, 1, 30, 31, 32)]
        self.assertEqual(coach.repeat_note(rows, 4), "'commit/PR/ticket text' asked 3x in the last 14 days")
        self.assertIsNone(coach.repeat_note(rows, 1))  # only 2 in the 14 days up to it
        self.assertIsNone(coach.repeat_note([(0, "p", "hello world friend")], 0))

    def test_keywords_match_whole_words_only(self):
        self.assertTrue(coach.has_kw("please review the diff now", "diff"))
        self.assertTrue(coach.has_kw("write a commit message.", "commit message"))
        self.assertFalse(coach.has_kw("a different approach", "diff"))
        self.assertFalse(coach.has_kw("i didn't ask", "dont"))

    def test_gold_labels_parse(self):
        r = gold.parse("### 1 gap=none\nhello there friend\nyours: ok\n\n### 2 gap=30\nfix it carefully\n"
                       "yours: no-vague, done-when\n\n### 3 gap=1\nx\nyours: \n")
        self.assertEqual(len(r), 2)
        self.assertEqual(r[1][2], {"no-vague", "done-when"})
        self.assertEqual(r[1][1], 30.0)


class Scripts(unittest.TestCase):
    def settings(self, cfg, data):
        with open(os.path.join(cfg, "settings.json"), "w") as f: json.dump(data, f)

    def test_uninstall_removes_only_the_old_coachline_statusline(self):
        old = {"type": "command", "command": "python C:/gone/plugins/cache/coachline/coachline/0.8.0/scripts/statusline.py"}
        with tempfile.TemporaryDirectory() as cfg:
            self.settings(cfg, {"theme": "dark", "statusLine": old})
            self.assertEqual(run("setup.py", cfg, "--uninstall").returncode, 0)
            s = read(os.path.join(cfg, "settings.json"))
            self.assertNotIn("statusLine", s); self.assertEqual(s["theme"], "dark")
            self.assertTrue(os.path.exists(os.path.join(cfg, "settings.json.coach-bak")))
            foreign = {"type": "command", "command": "other-tool"}
            self.settings(cfg, {"statusLine": foreign})
            run("setup.py", cfg, "--uninstall")
            self.assertEqual(read(os.path.join(cfg, "settings.json"))["statusLine"], foreign)      # someone else's statusline is untouched

    def test_refresh_migrates_the_old_statusline_away_and_never_fails_a_session_start(self):
        old = {"type": "command", "command": "python C:/gone/plugins/cache/coachline/coachline/0.8.0/scripts/statusline.py", "refreshInterval": 10}
        with tempfile.TemporaryDirectory() as cfg:
            self.settings(cfg, {"statusLine": old, "theme": "dark"})
            self.assertEqual(run("setup.py", cfg, "--refresh").returncode, 0)
            s = read(os.path.join(cfg, "settings.json"))
            self.assertNotIn("statusLine", s); self.assertEqual(s["theme"], "dark")
            self.assertTrue(os.path.isfile(os.path.join(cfg, "coach", "panel.py")))                # the stable launcher is refreshed too
            with open(os.path.join(cfg, "settings.json"), "w") as f: f.write("{broken")
            self.assertEqual(run("setup.py", cfg, "--refresh").returncode, 0)
            os.remove(os.path.join(cfg, "settings.json"))
            self.assertEqual(run("setup.py", cfg, "--refresh").returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(cfg, "settings.json")))                   # nothing to migrate: nothing created

    def test_setup_without_options_shows_the_settings_and_the_panel_command(self):
        with tempfile.TemporaryDirectory() as cfg:
            r = run("setup.py", cfg)
            self.assertEqual(r.returncode, 0, r.stderr)
            for want in ("Claude analysis (--panel-ai):  off", "auto-open a split pane (--auto-open):  off", "panel.py"):
                self.assertIn(want, r.stdout)
            self.assertFalse(os.path.exists(os.path.join(cfg, "settings.json")))                   # looking never writes settings

    def test_coach_and_doctor_on_real_shape_history(self):
        with tempfile.TemporaryDirectory() as cfg:
            with open(os.path.join(cfg, "history.jsonl"), "w") as f:
                f.write(json.dumps({"display": "please deal with this carefully " + "word " * 5, "timestamp": 5000, "project": "p"}) + "\n")
            out = run("coach.py", cfg, "--coach", "--no-llm").stdout
            self.assertIn("BEFORE (4/5)", out)
            d = run("coach.py", cfg, "--doctor")
            self.assertEqual(d.returncode, 0, d.stdout)
            self.assertIn("Claude analysis in the panel", d.stdout)
            self.assertIn("open the panel by hand:", d.stdout)


if __name__ == "__main__":
    unittest.main()
