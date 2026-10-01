import json, os, subprocess, sys, tempfile, time, unittest

from test_review import run, read
from test_watch import Base, T0
import coach, nudge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 30+ words, no "done"-style word, no risky verb, no vague word: fails exactly one rule (done-when)
LONG = ("please look at the invoice module and rework how it calculates the tax for every region because the current approach "
        "is hard to extend and the team finds it hard to read and maintain over time")
SOLID = LONG + " and verify the totals against last month"
SHORT = "rename total to grandTotal"
VAGUE = "handle this carefully and make it good for all the customers we have in every region right now"
# two gaps: long with no finish line, and a vague word
TWO = ("handle this carefully and make it good for all the customers we have in every region right now and also look at how the whole "
       "thing is organised across the many files of the project today")


def history(cfg, rows):
    """rows: (session, text); 90 s apart."""
    with open(os.path.join(cfg, "history.jsonl"), "w", encoding="utf-8") as f:
        for i, (sid, text) in enumerate(rows):
            f.write(json.dumps({"display": text, "timestamp": str(T0 + i * 90000), "project": "p", "sessionId": sid}) + "\n")


def statusline(cfg, session="now", **env):
    r = run(cfg, "statusline.py", STDIN=json.dumps({"session_id": session}), **env)
    assert r.returncode == 0, r.stderr
    return r.stdout.replace("\x1b[0m", "")                       # colour codes stay; only the resets are dropped


def plain(out):
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", out)


def heartbeat(cfg, age=0):
    os.makedirs(os.path.join(cfg, "coach"), exist_ok=True)
    p = os.path.join(cfg, "coach", "watch.alive")
    with open(p, "w") as f: f.write("x")
    if age: os.utime(p, (time.time() - age, time.time() - age))


class NeverStale(Base):
    def test_a_new_session_shows_nothing_about_a_previous_sessions_last_prompt(self):
        history(self.cfg, [("old", LONG)] * 8)
        heartbeat(self.cfg)
        out = plain(statusline(self.cfg, session="brand-new"))
        self.assertNotIn("last prompt", out)                      # that prompt belongs to another session
        self.assertNotIn("asked for", out)
        self.assertIn("next prompt: finish with \"Done when:", out)  # but forward-looking help from your history is welcome
        self.assertIn("your last 8 prompts", out)

    def test_the_same_session_gets_plain_english_feedback_on_its_last_prompt(self):
        history(self.cfg, [("now", LONG)] * 3)
        out = plain(statusline(self.cfg, session="now"))
        self.assertIn("last prompt: could be sharper -> say what proves it is done", out)
        self.assertNotIn("coach short", out)                       # the jargon that confused you
        self.assertNotIn("(/coach for before/after)", out)

    def test_it_says_when_everything_passes_and_stays_quiet_about_one_liners(self):
        history(self.cfg, [("now", SOLID)])
        self.assertIn("last prompt: passes all 5 checks", plain(statusline(self.cfg)))
        history(self.cfg, [("now", SHORT)])
        self.assertNotIn("last prompt", plain(statusline(self.cfg)))   # too short to judge: silence, not noise

    def test_a_missing_session_id_never_hides_the_feedback(self):
        history(self.cfg, [("now", LONG)])
        r = run(self.cfg, "statusline.py", STDIN="")
        self.assertIn("last prompt: could be sharper", plain(r.stdout))

    def test_garbage_or_unclosed_stdin_never_breaks_or_hangs_it(self):
        history(self.cfg, [("now", LONG)])
        self.assertIn("last prompt", plain(run(self.cfg, "statusline.py", STDIN="not json at all").stdout))
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.cfg, "PYTHONIOENCODING": "utf-8"}
        p = subprocess.Popen([sys.executable, os.path.join(ROOT, "scripts", "statusline.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env)
        try:
            t = time.time(); p.wait(timeout=10)                  # stdin is never written or closed
            self.assertLess(time.time() - t, 5)
            self.assertEqual(p.returncode, 0)
        finally:
            p.kill(); p.stdin.close(); p.stdout.close(); p.stderr.close()


class Trend(Base):
    def rows(self, texts): return [(T0 / 1000 + i * 90, "p", t) for i, t in enumerate(texts)]

    def test_top_gap_needs_a_real_pattern(self):
        t = nudge.tested(self.rows([LONG] * 5), 20)
        self.assertIsNone(nudge.top_gap(t))                         # fewer than 6 judged prompts
        t = nudge.tested(self.rows([LONG] * 7), 20)
        self.assertEqual(nudge.top_gap(t), ("done-when", 7, 7))
        mix = nudge.tested(self.rows([SOLID] * 9 + [LONG] * 2), 20)
        self.assertIsNone(nudge.top_gap(mix))                       # 2 of 11 is under 30%: not a pattern
        self.assertEqual(nudge.top_gap(nudge.tested(self.rows([SOLID] * 5 + [LONG] * 4), 20)), ("done-when", 4, 9))

    def test_one_liners_and_slash_commands_are_not_judged(self):
        t = nudge.tested(self.rows([SHORT, "continue", "/coach", LONG, SHORT]), 20)
        self.assertEqual([i for i, _f in t], [3])

    def test_the_sparkline_shows_gaps_per_prompt_and_needs_three_prompts(self):
        self.assertEqual(nudge.spark(nudge.tested(self.rows([LONG, SOLID]), 20)), "")
        self.assertEqual(nudge.spark(nudge.tested(self.rows([SOLID, LONG, TWO]), 20)), "█▅▃")   # none / one / two gaps
        self.assertEqual(len(nudge.spark(nudge.tested(self.rows([LONG] * 30), 20))), 10)

    def test_scanning_stops_early_so_a_huge_history_stays_fast(self):
        rows = self.rows([LONG] * 30000)
        t = time.time(); nudge.tested(rows, 20)
        self.assertLess(time.time() - t, 0.5)


class PanelHint(Base):
    def test_the_bottom_line_is_a_copy_paste_command_that_really_opens_the_panel(self):
        history(self.cfg, [("now", LONG)])
        last = plain(statusline(self.cfg)).strip().splitlines()[-1]
        self.assertTrue(last.startswith("panel not open -> paste this in a new terminal tab to open it: "), last)
        cmd = last.split(": ", 1)[1]
        shim = os.path.join(self.cfg, "coach", "panel.py")
        self.assertTrue(os.path.isfile(shim))
        self.assertIn(shim.replace("\\", "/"), cmd.replace("\\", "/").strip('"'))
        body = read(shim)
        self.assertIn(repr(os.path.join(ROOT, "scripts", "watch.py")), body)           # forwards to this version's watch.py
        r = subprocess.run([sys.executable, shim, "--once", "--width", "90", "--height", "10"], capture_output=True, text=True, encoding="utf-8",
                           env={**os.environ, "CLAUDE_CONFIG_DIR": self.cfg, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("THIS THREAD", r.stdout)   # the command works

    def test_no_hint_while_the_panel_is_open_and_it_returns_when_it_closes(self):
        history(self.cfg, [("now", LONG)])
        heartbeat(self.cfg)
        self.assertNotIn("panel not open", plain(statusline(self.cfg)))
        self.assertIn("(panel: e = rewrite)", plain(statusline(self.cfg)))        # and it points at the useful key
        heartbeat(self.cfg, age=60)                                              # the heartbeat went stale: the panel was closed
        self.assertIn("panel not open", plain(statusline(self.cfg)))

    def test_the_hint_can_be_switched_off(self):
        history(self.cfg, [("now", LONG)])
        self.assertEqual(run(self.cfg, "setup.py", "--panel-hint", "off").returncode, 0)
        self.assertNotIn("panel not open", plain(statusline(self.cfg)))
        run(self.cfg, "setup.py", "--panel-hint", "on")
        self.assertIn("panel not open", plain(statusline(self.cfg)))

    def test_paths_with_spaces_are_quoted_and_the_shim_follows_a_moved_plugin(self):
        with tempfile.TemporaryDirectory() as d:
            coach.STATE = os.path.join(d, "my coach dir")
            cmd = nudge.panel_command()
            self.assertIn('"', cmd); self.assertIn("my coach dir/panel.py", cmd)
            shim = os.path.join(coach.STATE, "panel.py")
            with open(shim, "w") as f: f.write("# stale shim from an older plugin version\n")
            nudge.ensure_shim()
            self.assertIn(repr(nudge.WATCH), read(shim))                                  # rewritten to point at the current version


class Helpers(Base):
    def test_last_session_reads_only_the_tail_and_survives_junk(self):
        self.assertEqual(coach.last_session(os.path.join(self.cfg, "missing.jsonl")), "")
        with open(self.path, "w", encoding="utf-8") as f:
            for i in range(3000): f.write(json.dumps({"display": "x" * 40, "timestamp": str(i), "sessionId": f"s{i}"}) + "\n")
            f.write("{broken line\n")
        self.assertEqual(coach.last_session(self.path), "s2999")

    def test_repeat_info_counts_a_kind_of_request_over_14_days(self):
        day = 86400; msg = "write a commit message for this"
        rows = [(i * day, "p", msg) for i in (0, 1, 2)]
        self.assertEqual(coach.repeat_info(rows, 2), ("commit/PR/ticket text", 3))
        self.assertIsNone(coach.repeat_info(rows, 1))
        self.assertEqual(coach.repeat_note(rows, 2), "'commit/PR/ticket text' asked 3x in the last 14 days")


if __name__ == "__main__":
    unittest.main()
