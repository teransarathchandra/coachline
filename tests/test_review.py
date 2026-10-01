import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE = os.path.join(ROOT, "tests", "fake_claude.py").replace("\\", "/")
PY = sys.executable.replace("\\", "/")

COMMIT = [f"write a commit message for change number {i} in this repo please" for i in range(6)]
STILL = [f"still broken after attempt {i}, not what i wanted please fix" for i in range(4)]
OTHER = [f"please explain topic {chr(97 + i)} in the module {i} of the parser" for i in range(10)]
GOOD_JSON = json.dumps({
    "requests": [
        {"name": "Commit Message", "description": "write commit messages", "steps": "1. read diff\n2. write one line", "keywords": ["commit message", "zzz invented"], "evidence": [1, 2, 3], "count": 99},
        {"name": "banana", "description": "x", "steps": "y", "keywords": ["banana"], "evidence": [1]},
    ],
    "mistakes": [
        {"name": "no-reason-correction", "problem": "corrects without a reason", "cost": "rework", "fix": "say which rule it broke", "template": "Rule broken: ...", "keywords": ["still broken"], "evidence": [7, 8, 9]},
        {"name": "generic", "problem": "p", "cost": "c", "fix": "f", "template": "t", "keywords": ["please"], "evidence": [7, 8]},
    ]})


def write_history(cfg, texts, project="proj"):
    path = os.path.join(cfg, "history.jsonl")
    n = 0
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f: n = sum(1 for _ in f)
    with open(path, "a", encoding="utf-8") as f:
        for i, t in enumerate(texts):
            f.write(json.dumps({"display": t, "timestamp": 1750000000000 + (n + i) * 90000, "project": project}) + "\n")


def run(cfg, script, *args, **env):
    e = {**os.environ, "CLAUDE_CONFIG_DIR": cfg, "PYTHONIOENCODING": "utf-8", "COACHLINE_CLAUDE": f'"{PY}" "{FAKE}"',
         "FAKE_LOG": os.path.join(cfg, "sent.log"), **env}
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", script), *args], capture_output=True, text=True, encoding="utf-8", env=e)


def read(p):
    with open(p, encoding="utf-8") as f: return f.read()


class Review(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.cfg = self.tmp.name
        write_history(self.cfg, COMMIT + STILL + OTHER)
        self.log = os.path.join(self.cfg, "sent.log"); self.state = os.path.join(self.cfg, "coach")

    def tearDown(self): self.tmp.cleanup()

    def test_plan_only_sends_nothing(self):
        r = run(self.cfg, "review.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Nothing has been sent", r.stdout)
        self.assertIn("20 prompts", r.stdout)
        self.assertFalse(os.path.exists(self.log))

    def test_results_are_grounded_locally(self):
        r = run(self.cfg, "review.py", "--yes", FAKE_JSON=GOOD_JSON)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        d = json.loads(read(os.path.join(self.state, "learned.json")))
        req = {x["name"]: x for x in d["requests"]}
        self.assertEqual(list(req), ["commit-message"])            # 'banana' dropped: not in its evidence
        self.assertEqual(req["commit-message"]["keywords"], ["commit message"])  # invented keyword dropped
        self.assertEqual(req["commit-message"]["count"], 6)        # recomputed locally, model said 99
        self.assertEqual([m["name"] for m in d["mistakes"]], ["no-reason-correction"])  # 'please' is too generic
        self.assertIn("banana", r.stdout)                          # dropped items are reported, not hidden
        self.assertTrue(os.path.isfile(os.path.join(self.state, "drafts", "commit-message", "SKILL.md")))
        self.assertTrue(any(f.startswith("review-") for f in os.listdir(self.state)))

    def test_accepts_the_shape_the_real_model_returns(self):
        # Observed from haiku: fenced JSON, evidence ids as strings, steps as a list.
        real = "```json\n" + json.dumps({"requests": [{"name": "commit-message-generation", "description": "commit messages",
            "steps": ["read diff", "write one line"], "keywords": ["commit message"], "evidence": ["1", "2", "#3"]}], "mistakes": []}) + "\n```"
        r = run(self.cfg, "review.py", "--yes", FAKE_JSON=real)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("1. read diff\n2. write one line", read(os.path.join(self.state, "drafts", "commit-message-generation", "SKILL.md")))
        self.assertEqual(json.loads(read(os.path.join(self.state, "learned.json")))["requests"][0]["count"], 6)

    def test_redaction_and_project_names_before_sending(self):
        write_history(self.cfg, ["mail a.b@example.org the report using password=hunter2 for the build"], project="secret-client-project")
        run(self.cfg, "review.py", "--yes", FAKE_JSON="{}")
        sent = read(self.log)
        for leaked in ("a.b@example.org", "hunter2", "secret-client-project"):
            self.assertNotIn(leaked, sent)
        self.assertIn("<email>", sent)

    def test_llm_off_projects_never_leave(self):
        write_history(self.cfg, ["migrate the confidential ledger tables to the new schema"], project="D:/work/employer-x")
        os.makedirs(self.state, exist_ok=True)
        with open(os.path.join(self.state, "llm-off.txt"), "w") as f: f.write("employer-x\n")
        r = run(self.cfg, "review.py", "--yes", FAKE_JSON="{}")
        self.assertNotIn("confidential ledger", read(self.log))
        self.assertIn("Excluded 1 prompts", r.stdout)

    def test_bad_output_and_failures_write_nothing(self):
        for mode in ("bad", "fail"):
            r = run(self.cfg, "review.py", "--yes", FAKE_MODE=mode)
            self.assertNotEqual(r.returncode, 0, mode)
            self.assertFalse(os.path.exists(os.path.join(self.state, "learned.json")), mode)

    def test_install_copies_once_and_rejects_bad_names(self):
        run(self.cfg, "review.py", "--yes", FAKE_JSON=GOOD_JSON)
        dst = os.path.join(self.cfg, "skills", "commit-message", "SKILL.md")
        self.assertEqual(run(self.cfg, "review.py", "--install", "commit-message").returncode, 0)
        self.assertIn("name: commit-message", read(dst))
        self.assertNotEqual(run(self.cfg, "review.py", "--install", "commit-message").returncode, 0)  # no overwrite
        self.assertNotEqual(run(self.cfg, "review.py", "--install", "../evil").returncode, 0)

    def test_it_records_how_much_it_saw_and_holds_a_lock_only_while_it_runs(self):
        lock = os.path.join(self.state, "review.running")
        run(self.cfg, "review.py", "--yes", FAKE_JSON=GOOD_JSON, FAKE_LOCK=lock)
        with open(self.log, encoding="utf-8") as f: self.assertIn("LOCK=True", f.read())      # held while Claude was being called
        self.assertFalse(os.path.exists(lock))                                              # and released afterwards
        with open(os.path.join(self.state, "learned.json"), encoding="utf-8") as f: d = json.load(f)
        self.assertEqual(d["prompts"], 20)                                                   # what this review analysed
        self.assertEqual(d["history_prompts"], 20)                                           # what the panel compares against later
        run(self.cfg, "review.py", "--yes", FAKE_MODE="fail", FAKE_LOCK=lock)
        self.assertFalse(os.path.exists(lock))                                              # released even when every call failed

    def test_the_panel_shows_what_claude_found_when_this_thread_repeats_it(self):
        run(self.cfg, "review.py", "--yes", FAKE_JSON=GOOD_JSON)
        out = " ".join(run(self.cfg, "watch.py", "--once", "--width", "120", "--height", "40").stdout.split())
        self.assertIn('You have asked for "commit-message"', out)
        self.assertIn("make it a skill, /commit-message (a draft is ready: press s to install it)", out)
        self.assertIn("Recurring gap", out)

    def test_install_skill_returns_a_message_instead_of_exiting(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import review
        saved = (review.coach.STATE, review.coach.CONFIG)
        review.coach.STATE, review.coach.CONFIG = self.state, self.cfg
        try:
            run(self.cfg, "review.py", "--yes", FAKE_JSON=GOOD_JSON)
            ok, msg = review.install_skill("commit-message")
            self.assertTrue(ok); self.assertIn("installed", msg)
            ok, msg = review.install_skill("commit-message")
            self.assertFalse(ok); self.assertIn("not overwriting", msg)
            self.assertEqual(review.install_skill("../evil")[0], False)
            self.assertEqual(review.install_skill("no-such-draft")[0], False)
        finally:
            review.coach.STATE, review.coach.CONFIG = saved


class Quality(unittest.TestCase):
    def test_requests_need_phrase_keywords_and_names_are_cut_at_a_word_boundary(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import review
        items = [{"id": i, "ts": i, "proj": "P1", "gap": 5, "text": t.lower()} for i, t in enumerate(
            ["merge the pr and update the install now", "merge the pr and update the install again", "merge the pr and update the install please",
             "install this tool for me", "install that tool for me", "install another tool for me",
             "explain the cache layer", "rename the user table", "write tests for billing", "profile the slow endpoint"], 1)]
        res = [{"requests": [{"name": "merge-prs", "description": "d", "steps": "s", "keywords": ["merge the pr and update"], "evidence": [1, 2, 3]},
                             {"name": "install-things", "description": "d", "steps": "s", "keywords": ["tool"], "evidence": [4, 5, 6]}], "mistakes": []}]
        requests, _m, dropped = review.ground(res, items)
        self.assertEqual([r["name"] for r in requests], ["merge-prs"])                       # a single generic word does not define a repeated task
        self.assertTrue(any("only single-word keywords" in d for d in dropped))
        slug = review._slug("merge-prs-and-update-the-install-for-iterative-plugin-releases")
        self.assertLessEqual(len(slug), 32)
        self.assertTrue("merge-prs-and-update-the-install-for-iterative-plugin-releases".startswith(slug + "-"))   # whole words only


if __name__ == "__main__":
    unittest.main()
