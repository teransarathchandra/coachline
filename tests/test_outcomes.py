"""The outcome loop: turns you interrupted and follow-ups that correct a prompt, kept on this machine as evidence."""
import json, os, subprocess, sys, time, unittest

from test_state import Base, load
import coach

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Outcomes(Base):
    def setUp(self):
        super().setUp()
        self._out = coach.OUTCOMES; coach.OUTCOMES = os.path.join(self.state, "outcomes.jsonl")

    def tearDown(self):
        coach.OUTCOMES = self._out; super().tearDown()

    def lines(self):
        try:
            with open(coach.OUTCOMES, encoding="utf-8") as f: return [json.loads(l) for l in f if l.strip()]
        except OSError: return []

    def test_corrections_open_with_a_correction(self):
        for t in ("no, I meant the header", "No. The other file", "nope", "that's wrong, revert it", "that’s not it", "undo that please",
                  "not quite, the header", "wait, I meant the footer", "I meant the footer"):
            self.assertTrue(coach.is_correction(t), t)
        for t in ("still failing on CI", "now add tests", "nothing else", "know what? add tests", "not working yet, keep going",
                  "no worries, now add tests", "No need to touch the docs", "Actually also add a test", "revert the migration in db/0042.py",
                  "no-op the logger in prod"):
            self.assertFalse(coach.is_correction(t), t)

    def test_record_outcome_keeps_a_redacted_head_not_the_prompt(self):
        self.assertTrue(coach.record_outcome("aborted", "fix it now please", now=1000.0))
        self.assertTrue(coach.record_outcome("corrected", "mail bob@example.com the long report about the quarterly numbers", now=1001.0))
        a, b = self.lines()
        self.assertEqual(a, {"v": 1, "ts": 1000.0, "kind": "aborted", "vague": True, "cells": a["cells"], "head": "fix it now please"})
        self.assertEqual(b["head"], "mail <email> the long")
        self.assertNotIn("quarterly", json.dumps(b))

    def test_a_correction_after_an_interrupt_counts_once(self):
        coach.record_outcome("aborted", "make it look nicer please", now=1000.0)
        self.assertFalse(coach.record_outcome("corrected", "make it look nicer please", now=1100.0))
        self.assertTrue(coach.record_outcome("corrected", "make it look nicer please", now=1000.0 + 3600))     # a later, separate one
        self.assertEqual([l["kind"] for l in self.lines()], ["aborted", "corrected"])

    def test_secrets_in_the_head_are_redacted(self):
        coach.record_outcome("aborted", "DB_PASSWORD=hunter2 breaks the deploy now", now=1.0)
        coach.record_outcome("aborted", "my password is hunter2 so log in", now=2.0)
        self.assertNotIn("hunter2", json.dumps(self.lines()))

    def test_commands_are_never_recorded(self):
        for t in ("/clear", "!ls -la now", "# note this down", "yes"):
            self.assertFalse(coach.record_outcome("aborted", t), t)
        self.assertEqual(self.lines(), [])

    def test_appends_from_many_processes_stay_whole(self):
        code = ("import sys; sys.path.insert(0, %r); import coach; coach.OUTCOMES = %r; "
                "[coach.record_outcome('aborted', 'fix the login page now %%d' %% i) for i in range(20)]") % (os.path.join(ROOT, "scripts"), coach.OUTCOMES)
        ps = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(3)]
        for p in ps: self.assertEqual(p.wait(), 0)
        self.assertEqual(len(self.lines()), 60)

    def test_sweep_keeps_90_days(self):
        now = time.time()
        coach.record_outcome("aborted", "fix it now please", now=now - 91 * 86400)
        coach.record_outcome("aborted", "fix it again please", now=now - 86400)
        coach.sweep(now=now)
        self.assertEqual([l["head"] for l in self.lines()], ["fix it again please"])

    def test_forget_outcomes_only(self):
        coach.record_outcome("aborted", "fix it now please")
        self.put("rewrites.jsonl")
        coach.forget("outcomes")
        self.assertFalse(os.path.exists(coach.OUTCOMES)); self.assertTrue(os.path.exists(os.path.join(self.state, "rewrites.jsonl")))

    def run_pane(self, *args, stdin=""):
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.tmp.name}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "pane.py"), *args], input=stdin.encode("utf-8"), capture_output=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(r.stdout, b"")

    def test_pane_records_from_stdin(self):
        path = os.path.join(self.tmp.name, "coach", "outcomes.jsonl")
        self.run_pane("--outcome", "aborted", stdin="fix it now please")
        self.run_pane("--outcome", "next", stdin=json.dumps({"prev": "make it look nicer please", "text": "no, I meant the header"}))
        self.run_pane("--outcome", "next", stdin=json.dumps({"prev": "make it look nicer please", "text": "now add tests"}))
        self.run_pane("--outcome", "next", stdin="not json")
        with open(path, encoding="utf-8") as f: kinds = [json.loads(l)["kind"] for l in f]
        self.assertEqual(kinds, ["aborted", "corrected"])


    VAGUE = ["make it look nicer " + w for w in ("please", "today", "again", "now", "quickly", "soon")]
    CONCRETE = ["fix the typo in README.md line %d" % i for i in range(10)]

    def history_rows(self, now):
        return [(now - 3600 * (i + 1), "p", t, "s") for i, t in enumerate(self.VAGUE + self.CONCRETE)]

    def test_no_evidence_line_below_three_events(self):
        now = time.time()
        for t in self.VAGUE[:2]: coach.record_outcome("aborted", t, now=now - 60)
        self.assertIsNone(coach.evidence_line(self.history_rows(now), now=now))

    def test_evidence_line_compares_vague_with_concrete(self):
        now = time.time()
        for t in self.VAGUE[:3]: coach.record_outcome("aborted", t, now=now - 60)
        coach.record_outcome("corrected", self.CONCRETE[0], now=now - 60)
        coach.record_outcome("aborted", self.VAGUE[0], now=now - 20 * 86400)                 # older than 14 days: not counted
        self.assertEqual(coach.evidence_line(self.history_rows(now), now=now),
                         "Vague prompts led to rework 3 of 6 times in 14 days; concrete ones 1 of 10")

    def test_the_evidence_line_leads_the_patterns(self):
        import watch
        st = {"insights": [], "evidence": "Vague prompts led to rework 3 of 6 times in 14 days; concrete ones 1 of 10"}
        self.assertEqual(watch.pattern_texts(st), [st["evidence"]])
        self.assertEqual(watch.pattern_texts({"insights": []}), [])
        base = {"session": "s", "entries": [], "insights": [], "learned": {}, "review_running": False, "ai": True}
        self.assertNotEqual(watch.signature(base), watch.signature(dict(base, evidence=st["evidence"])))   # a new line redraws the panel


if __name__ == "__main__":
    unittest.main()
