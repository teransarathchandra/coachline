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

    def test_doctor_and_reinstall_work_from_a_folder_with_a_space_and_any_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = os.path.join(tmp, "cfg"); os.makedirs(cfg)
            for name in ("with space", "renamed"):
                dst = os.path.join(tmp, name, "scripts")
                shutil.copytree(os.path.join(ROOT, "scripts"), dst, ignore=shutil.ignore_patterns("__pycache__"))
                env = {**os.environ, "CLAUDE_CONFIG_DIR": cfg}
                def cmd(script, *a):
                    return subprocess.run([sys.executable, os.path.join(dst, script), *a],
                                          capture_output=True, text=True, env=env)
                self.assertEqual(cmd("setup.py").returncode, 0, name + " setup")
                out = cmd("coach.py", "--doctor")
                self.assertIn("statusline script exists", out.stdout, name)
                self.assertNotIn("FAIL statusline", out.stdout, name)

    def test_refresh_repoints_only_our_own_stale_entry(self):
        with tempfile.TemporaryDirectory() as cfg:
            sp = os.path.join(cfg, "settings.json")
            stale = {"type": "command", "command": "python /gone/plugins/cache/coachline/coachline/0.1.0/scripts/statusline.py"}
            with open(sp, "w") as f: json.dump({"statusLine": stale}, f)
            self.assertEqual(run("setup.py", cfg, "--refresh").returncode, 0)
            self.assertIn(os.path.join(ROOT, "scripts").replace("\\", "/"), read(sp)["statusLine"]["command"])
            foreign = {"type": "command", "command": "other-tool"}
            with open(sp, "w") as f: json.dump({"statusLine": foreign}, f)
            run("setup.py", cfg, "--refresh"); self.assertEqual(read(sp)["statusLine"], foreign)
            os.remove(sp); run("setup.py", cfg, "--refresh"); self.assertFalse(os.path.exists(sp))
            with open(sp, "w") as f: f.write("{broken")
            self.assertEqual(run("setup.py", cfg, "--refresh").returncode, 0)  # never fail a session start

    def test_statusline_stays_fast_on_a_huge_history(self):
        import time
        with tempfile.TemporaryDirectory() as cfg:
            with open(os.path.join(cfg, "history.jsonl"), "w") as f:
                for i in range(30000):
                    f.write(json.dumps({"display": "write a commit message for this change please",
                                        "timestamp": 1750000000000 + i * 60000, "project": "p"}) + "\n")
            t = time.time(); r = run("statusline.py", cfg)
            self.assertEqual(r.returncode, 0)
            self.assertLess(time.time() - t, 5, "was 13s before the O(n) fix")

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
