import json, os, subprocess, sys, tempfile, unittest

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

    def test_gold_labels_parse(self):
        r = gold.parse("### 1 gap=none\nhello there friend\nyours: ok\n\n### 2 gap=30\nfix it carefully\n"
                       "yours: no-vague, done-when\n\n### 3 gap=1\nx\nyours: \n")
        self.assertEqual(len(r), 2)
        self.assertEqual(r[1][2], {"no-vague", "done-when"})
        self.assertEqual(r[1][1], 30.0)


class Scripts(unittest.TestCase):
    def test_setup_installs_refuses_foreign_and_uninstalls(self):
        with tempfile.TemporaryDirectory() as cfg:
            sp = os.path.join(cfg, "settings.json")
            with open(sp, "w") as f: json.dump({"theme": "dark"}, f)
            self.assertEqual(run("setup.py", cfg).returncode, 0)
            s = read(sp)
            self.assertIn("statusline.py", s["statusLine"]["command"])
            self.assertEqual(s["theme"], "dark")
            self.assertTrue(os.path.exists(sp + ".coach-bak"))
            self.assertEqual(run("setup.py", cfg, "--uninstall").returncode, 0)
            self.assertNotIn("statusLine", read(sp))
            with open(sp, "w") as f: json.dump({"statusLine": {"type": "command", "command": "other"}}, f)
            self.assertNotEqual(run("setup.py", cfg).returncode, 0)
            self.assertEqual(read(sp)["statusLine"]["command"], "other")

    def test_statusline_never_fails_on_empty_config(self):
        with tempfile.TemporaryDirectory() as cfg:
            r = run("statusline.py", cfg)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, ""))

    def test_statusline_and_coach_on_real_shape_history(self):
        with tempfile.TemporaryDirectory() as cfg:
            with open(os.path.join(cfg, "history.jsonl"), "w") as f:
                f.write(json.dumps({"display": "please deal with this carefully " + "word " * 5, "timestamp": 5000, "project": "p"}) + "\n")
            self.assertIn("no-vague", run("statusline.py", cfg).stdout)
            out = run("coach.py", cfg, "--coach", "--no-llm").stdout
            self.assertIn("BEFORE (4/5)", out)
            self.assertNotEqual(run("coach.py", cfg, "--doctor").returncode, 2)


if __name__ == "__main__":
    unittest.main()
