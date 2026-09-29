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

    def test_statusline_shows_learned_habit_without_any_llm(self):
        run(self.cfg, "review.py", "--yes", FAKE_JSON=GOOD_JSON)
        os.remove(self.log)
        write_history(self.cfg, ["still broken again after the last change, not sure why it fails"])
        r = run(self.cfg, "statusline.py")
        self.assertIn("habit: no-reason-correction", r.stdout)
        self.assertFalse(os.path.exists(self.log))


if __name__ == "__main__":
    unittest.main()
