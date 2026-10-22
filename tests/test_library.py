"""The prompt library: prompts that worked first time, kept on this machine, offered again for a similar draft."""
import json, os, subprocess, sys, time, unittest
from unittest import mock

from test_state import Base
import coach, library

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD = "add pagination to the orders table with 25 rows per page and keep the current sort order intact"
OTHER = "write a migration that adds an index on the created_at column of the events table in postgres"


class Library(Base):
    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.tmp.name, "shop"); os.makedirs(self.proj)
        with open(os.path.join(self.proj, "package.json"), "w") as f: json.dump({"dependencies": {"react": "^19.0.0", "next": "15.0.0"}}, f)

    def worked(self, text, project=None, now=None):
        self.assertTrue(library.candidate(text, project or self.proj, now=now))
        library.followup("now add a test for the empty page", project=project or self.proj, now=now)
        library.followup("and update the readme section", project=project or self.proj, now=now)

    def texts(self, project=None):
        return [e["text"] for e in library.entries(project)]

    def test_a_prompt_with_two_clean_followups_is_saved(self):
        self.worked(GOOD)
        self.assertEqual(self.texts(self.proj), [GOOD])
        e = library.entries(self.proj)[0]
        self.assertEqual((e["uses"], e["off"], len(e["id"])), (0, False, 12)); self.assertIn("react", e["stack"])

    def test_a_corrected_prompt_is_never_saved(self):
        library.candidate(GOOD, self.proj)
        library.followup("no, I meant the users table", prev=GOOD, project=self.proj)
        library.followup("now add a test for the empty page", project=self.proj); library.followup("and update the readme section", project=self.proj)
        self.assertEqual(self.texts(), [])

    def test_a_correction_without_its_prompt_drops_nothing(self):
        library.candidate(GOOD, self.proj)
        library.followup("no, I meant the users table", project=self.proj)
        library.followup("now add a test for the empty page", project=self.proj); library.followup("and update the readme section", project=self.proj)
        self.assertEqual(self.texts(), [GOOD])

    def test_another_projects_prompts_are_no_follow_up(self):
        elsewhere = os.path.join(self.tmp.name, "elsewhere")
        library.candidate(GOOD, self.proj)
        library.followup("now add a test for the empty page", project=elsewhere); library.followup("and update the readme section", project=elsewhere)
        self.assertEqual(self.texts(), [])

    def test_the_same_prompt_is_saved_in_each_project_and_forgotten_separately(self):
        same = self.other_project({"react": "^19.0.0"})
        self.worked(GOOD); self.worked(GOOD, project=same)
        self.assertEqual((self.texts(self.proj), self.texts(same)), ([GOOD], [GOOD]))
        library.forget(library.entries(self.proj)[0]["id"])
        self.assertEqual((self.texts(self.proj), self.texts(same)), ([], [GOOD]))

    def test_a_full_library_still_takes_a_new_prompt(self):
        for i in range(library.CAP_PROJECT): self.worked(f"{GOOD} variant {i:03d}", now=1000.0 + i)
        for e in library.entries(self.proj): library.used(e["id"])
        self.worked(GOOD + " brand new", now=9000.0)
        self.assertIn(GOOD + " brand new", self.texts(self.proj))
        self.assertEqual(len(self.texts(self.proj)), library.CAP_PROJECT)

    def test_a_correction_that_arrives_before_its_candidate_still_counts(self):
        library.followup("no, I meant the users table", prev=GOOD, project=self.proj)    # typed while the turn still ran
        self.assertFalse(library.candidate(GOOD, self.proj))
        self.assertTrue(library.candidate(GOOD, self.proj))                              # one veto, one prompt: a later run is judged anew

    def test_forget_waits_for_a_promotion_in_another_tab(self):
        import threading
        self.worked(GOOD); i = library.entries()[0]["id"]
        with library._lock():
            t = threading.Thread(target=library.forget, args=(i,)); t.start()
            time.sleep(0.3); self.assertTrue(t.is_alive())                               # waits while another tab writes
        t.join(5); self.assertEqual(library.entries(), [])

    def test_this_projects_prompt_wins_a_tie(self):
        same = self.other_project({"react": "^19.0.0"})
        self.worked(GOOD, project=same)
        for _ in range(3): library.used(library.entries(same)[0]["id"])
        self.worked(GOOD)
        self.assertEqual(library.match(self.NEAR, self.proj)["id"], library.entries(self.proj)[0]["id"])

    def test_a_near_duplicate_still_matches_and_a_thin_entry_never_does(self):
        self.worked(GOOD)
        self.assertIsNotNone(library.match(GOOD.replace("25", "50"), self.proj))
        self.worked("can you please fix it so that it works the way it should now for me")
        self.assertIsNone(library.match("fix whatever works", self.proj))

    def test_the_prompt_itself_is_no_similar_one(self):
        self.worked(GOOD)
        self.assertIsNone(library.match(GOOD, self.proj))

    def test_short_commands_and_secrets(self):
        self.assertFalse(library.candidate("add pagination to the orders table with 25 rows", self.proj))       # 11 words
        self.assertFalse(library.candidate("/frontend-design " + GOOD, self.proj))
        self.assertFalse(library.candidate("!" + GOOD, self.proj))
        self.worked(GOOD + " and use token=sk-live-1234567890abcdef")
        self.assertNotIn("sk-live", json.dumps(library.entries()))

    def test_a_quiet_day_promotes_a_candidate(self):
        now = time.time()
        library.candidate(GOOD, self.proj, now=now - 25 * 3600)
        library.promote_due(now=now)
        self.assertEqual(self.texts(), [GOOD])

    def test_caps_drop_the_least_used(self):
        for i in range(205): self.worked(f"{GOOD} variant {i:03d}", now=1000.0 + i)
        kept = library.entries(self.proj)
        self.assertEqual(len(kept), library.CAP_PROJECT)
        oldest = kept[-3:]                                           # the first to go, unless used
        for e in oldest: library.used(e["id"])
        self.worked(GOOD + " one more", now=5000.0)
        ids = {e["id"] for e in library.entries(self.proj)}
        self.assertTrue(all(e["id"] in ids for e in oldest))

    def test_forget_and_used(self):
        self.worked(GOOD); i = library.entries()[0]["id"]
        library.used(i); self.assertEqual(library.entries()[0]["uses"], 1)
        self.assertTrue(library.forget(i)); self.assertEqual(library.entries(), [])
        self.assertFalse(library.forget(i))

    def test_two_processes_promoting_leave_valid_json(self):
        code = ("import sys; sys.path.insert(0, %r); import coach; coach.STATE = %r; import library\n"
                "for i in range(15):\n library.candidate(%r + ' run %%d' %% i, %r); library.followup('now add a test for it please', project=%r); "
                "library.followup('and update the readme section', project=%r)") % (os.path.join(ROOT, "scripts"), self.state, GOOD, self.proj, self.proj, self.proj)
        ps = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(2)]
        for p in ps: self.assertEqual(p.wait(), 0)
        with open(os.path.join(self.state, "library.json"), encoding="utf-8") as f: items = json.load(f)["items"]
        self.assertGreaterEqual(len(items), 15)                                           # the lock: no promotion lost

    NEAR = "add pagination to the users table with 25 rows per page and keep the sort"

    def other_project(self, deps, off=False):
        p = os.path.join(self.tmp.name, "other" + str(len(deps)) + str(off)); os.makedirs(p)
        with open(os.path.join(p, "package.json"), "w") as f: json.dump({"dependencies": deps}, f)
        if off:
            with open(coach.OFF, "w") as f: f.write(p + "\n")
        return p

    def test_a_similar_draft_matches_and_an_unrelated_one_does_not(self):
        self.worked(GOOD)
        self.assertEqual(library.match(self.NEAR, self.proj)["text"], GOOD)
        self.assertIsNone(library.match(OTHER, self.proj))
        self.assertIsNone(library.match("", self.proj))

    def test_other_projects_match_only_on_a_shared_framework_and_never_when_private(self):
        same = self.other_project({"react": "^19.0.0"}); diff = self.other_project({"vue": "^3.0.0", "pinia": "^2.0.0"})
        self.worked(GOOD, project=same)
        self.assertEqual(library.match(self.NEAR, self.proj)["text"], GOOD)
        self.assertIsNone(library.match(self.NEAR, diff))
        library.forget(library.entries()[0]["id"])
        private = self.other_project({"react": "^19.0.0", "next": "15.0.0"}, off=True)
        self.worked(GOOD, project=private)
        self.assertIsNone(library.match(self.NEAR, self.proj))
        self.assertEqual(library.match(self.NEAR, private)["text"], GOOD)        # its own project still sees it

    def test_score_returns_the_match(self):
        import pane
        self.worked(GOOD)
        self.assertEqual(pane.score(self.NEAR, project=self.proj)["match"]["text"], GOOD)
        self.assertIsNone(pane.score(OTHER, project=self.proj)["match"])
        self.assertIsNone(pane.score(self.NEAR)["match"])
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.tmp.name}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "pane.py"), "--score", "--project", self.proj],
                           input=self.NEAR.encode(), capture_output=True, env=env)
        self.assertEqual(json.loads(r.stdout)["match"]["text"], GOOD, r.stderr)

    def test_the_pane_state_lists_this_projects_library(self):
        import pane
        self.worked(GOOD)
        with mock.patch.object(coach, "HIST", os.path.join(self.tmp.name, "history.jsonl")):
            st = pane.tick("s1", width=80, project=self.proj)
            self.assertEqual([(e["text"], e["uses"]) for e in st["library"]], [(GOOD, 0)])
            self.assertEqual(pane.tick("s1", width=80, project=os.path.join(self.tmp.name, "elsewhere"))["library"], [])

    def test_pane_library_used_and_forget(self):
        self.worked(GOOD); i = library.entries()[0]["id"]
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.tmp.name}
        def pane(*args):
            return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "pane.py"), *args], capture_output=True, env=env).returncode
        self.assertEqual(pane("--library", "used", i), 0); self.assertEqual(library.entries()[0]["uses"], 1)      # same state folder
        self.assertEqual(pane("--library", "forget", i), 0); self.assertEqual(library.entries(), [])
        self.assertEqual(pane("--library", "forget", i), 1)
        self.assertEqual(pane("--library", "bogus", i), 2)

    def test_forget_library_removes_both_files_and_nothing_else(self):
        library.candidate(GOOD, self.proj); self.worked(GOOD + " again"); self.put("rewrites.jsonl")
        library.candidate(OTHER + " and keep the old one", self.proj)
        coach.forget("library")
        self.assertEqual(sorted(os.listdir(self.state)), ["rewrites.jsonl"])

    def test_a_correction_drops_the_prompt_it_answers_even_out_of_order(self):
        library.candidate(OTHER, self.proj)
        library.candidate(GOOD, self.proj)
        library.followup("no, I meant the other index", prev=OTHER, project=self.proj)             # answers OTHER, though GOOD is newer
        library.followup("now add a test for the empty page", project=self.proj); library.followup("and update the readme section", project=self.proj)
        self.assertEqual(self.texts(), [GOOD])

    def test_a_project_put_in_llm_off_later_is_not_offered_elsewhere(self):
        same = self.other_project({"react": "^19.0.0"})
        self.worked(GOOD, project=same)
        self.assertIsNotNone(library.match(self.NEAR, self.proj))
        with open(coach.OFF, "w") as f: f.write(same)
        self.assertIsNone(library.match(self.NEAR, self.proj))

    def test_pane_outcome_done_from_stdin(self):
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.tmp.name}
        def pane(*args, stdin):
            r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "pane.py"), *args], input=stdin.encode(), capture_output=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
        pane("--outcome", "done", stdin=json.dumps({"text": GOOD, "project": self.proj}))
        for t in ("now add a test for the empty page", "and update the readme section"):
            pane("--outcome", "next", stdin=json.dumps({"prev": GOOD, "text": t, "project": self.proj}))
        with open(os.path.join(self.tmp.name, "coach", "library.json"), encoding="utf-8") as f:
            self.assertEqual([e["text"] for e in json.load(f)["items"]], [GOOD])


if __name__ == "__main__":
    unittest.main()
