import json, os, subprocess, sys, tempfile, time, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import coach, pane  # noqa: E402
from test_watch import history, VAGUE, SOLID  # noqa: E402

NOTICE = "Claude analysis is on: prompts go redacted to your subscription, task topics to web search · /coach panel-ai off"


class FakeIO:
    def __init__(self): self.enhanced, self.reviews = [], 0
    def enhance(self, key): self.enhanced.append(key)
    def review(self): self.reviews += 1


class Tick(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); c = self.cfg = self.tmp.name
        self.saved = (coach.CONFIG, coach.HIST, coach.STATE, coach.USER_CFG, coach.ALIVE, coach.REWRITES, coach.LEARNED, coach.REVIEW_LOCK)
        coach.CONFIG, coach.HIST, coach.STATE = c, os.path.join(c, "history.jsonl"), os.path.join(c, "coach")
        coach.USER_CFG, coach.ALIVE = os.path.join(coach.STATE, "config.json"), os.path.join(coach.STATE, "watch.alive")
        coach.REWRITES, coach.LEARNED = os.path.join(coach.STATE, "rewrites.jsonl"), os.path.join(coach.STATE, "learned.json")
        coach.REVIEW_LOCK = os.path.join(coach.STATE, "review.running")
        os.makedirs(coach.STATE)
        self.env = mock.patch.dict(os.environ, {"COACHLINE_PLATFORM": "Darwin"}); self.env.start()
        self.io = FakeIO()

    def tearDown(self):
        self.env.stop()
        (coach.CONFIG, coach.HIST, coach.STATE, coach.USER_CFG, coach.ALIVE, coach.REWRITES, coach.LEARNED, coach.REVIEW_LOCK) = self.saved
        self.tmp.cleanup()

    def tick(self, session="s1", now=None):
        return pane.tick(session, width=80, io=self.io, now=now)

    def test_it_returns_only_this_sessions_prompts_with_card_lines(self):
        history(self.cfg, [("s1", "p", VAGUE), ("s2", "p", SOLID)])
        st = self.tick()
        self.assertEqual(st["session"], "s1")
        self.assertEqual([e["text"] for e in st["entries"]], [VAGUE])
        lines = st["entries"][0]["lines"]
        self.assertEqual(lines[0][:3], ["prompt", "head", "Your prompt"])
        self.assertTrue(all(len(l) == 5 for l in lines))
        json.dumps(st)                                                     # it must be JSON-safe

    def test_a_new_session_with_no_prompts_is_empty(self):
        history(self.cfg, [("old", "p", VAGUE)])
        st = self.tick("brand-new")
        self.assertEqual(st["entries"], [])
        self.assertEqual(self.io.enhanced, [])

    def test_it_queues_the_newest_unanalysed_prompt_when_analysis_is_on(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        st = self.tick()
        self.assertEqual(len(self.io.enhanced), 1)
        self.assertEqual(st["entries"][0]["state"], "pending")

    def test_a_second_tick_does_not_queue_the_same_prompt_again(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        t = time.time()
        self.tick(now=t); self.tick(now=t + 3)
        self.assertEqual(len(self.io.enhanced), 1)

    def test_no_autopilot_while_a_standalone_panel_is_open(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        open(coach.ALIVE, "w").close()
        self.tick()
        self.assertEqual(self.io.enhanced, [])

    def test_nothing_is_queued_when_the_user_turned_analysis_off(self):
        coach.set_setting("panel_ai", False)
        history(self.cfg, [("s1", "p", VAGUE)])
        st = self.tick()
        self.assertEqual(self.io.enhanced, []); self.assertFalse(st["ai"])

    def test_the_notice_shows_in_the_first_three_sessions_only(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        for sid in ("a", "b", "c"):
            self.assertEqual(self.tick(sid)["notice"], NOTICE)
            self.assertEqual(self.tick(sid)["notice"], NOTICE)           # still shown on the next tick of the same session
        self.assertIsNone(self.tick("d")["notice"])

    def test_no_notice_once_the_user_chose(self):
        coach.set_setting("panel_ai", True)
        self.assertIsNone(self.tick()["notice"])

    def test_a_tick_already_running_for_this_session_queues_nothing(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        open(pane.lock_path("s1"), "w").close()                           # another pane.py for s1 is mid-tick
        st = self.tick()
        self.assertEqual(self.io.enhanced, [])
        self.assertEqual([e["text"] for e in st["entries"]], [VAGUE])      # it still answers with the state

    def test_a_stale_lock_is_ignored(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        open(pane.lock_path("s1"), "w").close(); os.utime(pane.lock_path("s1"), (0, 0))
        self.tick()
        self.assertEqual(len(self.io.enhanced), 1)
        self.assertFalse(os.path.exists(pane.lock_path("s1")))             # released after the tick

    def test_a_standalone_panel_on_another_session_does_not_stop_this_one(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        open(coach.ALIVE, "w").close()
        with open(os.path.join(coach.STATE, "watch.session"), "w") as f: f.write("s2")
        self.tick()
        self.assertEqual(len(self.io.enhanced), 1)

    def test_a_standalone_panel_on_this_session_does_the_work(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        open(coach.ALIVE, "w").close()
        with open(os.path.join(coach.STATE, "watch.session"), "w") as f: f.write("s1")
        self.tick()
        self.assertEqual(self.io.enhanced, [])

    def test_with_auto_open_off_nothing_is_sent_and_no_notice_is_used_up(self):
        coach.set_setting("auto_open_watch", False)
        history(self.cfg, [("s1", "p", VAGUE)])
        st = self.tick()
        self.assertEqual(self.io.enhanced, []); self.assertEqual(self.io.reviews, 0)
        self.assertIsNone(st["notice"])
        self.assertEqual(coach.setting("notice_sessions", []), [])

    def test_the_cli_prints_json(self):
        history(self.cfg, [("s1", "p", VAGUE)])
        coach.set_setting("panel_ai", False)                              # the subprocess must not spawn a real `claude`
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.cfg, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "pane.py"), "--json", "--session", "s1", "--width", "60"],
                           capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["entries"][0]["text"], VAGUE)


    def write_rec(self, rec):
        with open(coach.REWRITES, "a", encoding="utf-8") as f: f.write(json.dumps(rec) + "\n")

    def test_web_suggestions_come_with_hide_and_use_actions(self):
        history(self.cfg, [("s1", "p", SOLID)])
        from test_watch import key_for, ADVICE
        self.write_rec({"key": key_for(0, SOLID), "text": "AFTER: x", "advice": ADVICE,
                        "discovery": [{"name": "GreatKit", "kind": "tool", "why": "w", "url": "https://x.example.com/g", "install": "", "stars": None, "pushed": None}]})
        st = self.tick()
        self.assertIn(["web", "itemacts", "", "", "item:x.example.com/g"], st["entries"][0]["lines"])
        self.assertIn("References (checked links from web research):", st["entries"][0]["after"])

    def test_mark_and_research_from_the_pane(self):
        import memory
        self.assertEqual(pane.main(["--mark", "dismissed", "x.example.com/g"]), 0)
        self.assertEqual(memory.statuses(), {"x.example.com/g": "dismissed"})
        self.assertEqual(pane.main(["--mark", "maybe", "x.example.com/g"]), 2)
        with mock.patch.object(coach, "spawn_research") as sr:
            self.assertEqual(pane.main(["--research", "123.0:abc", "--session", "s1"]), 0)
        sr.assert_called_once_with("123.0:abc")

class Actions(unittest.TestCase):
    def test_enhance_starts_one_background_analysis(self):
        with mock.patch.object(coach, "spawn_key") as spawn, mock.patch("sys.stdout"):
            self.assertEqual(pane.main(["--enhance", "123.0:abc"]), 0)
        spawn.assert_called_once_with("123.0:abc")

    def test_analyse_with_a_session_marks_the_prompt_as_sent(self):
        with tempfile.TemporaryDirectory() as d:
            saved = coach.STATE; coach.STATE = d
            try:
                with mock.patch.object(coach, "spawn_key"), mock.patch("sys.stdout"):
                    self.assertEqual(pane.main(["--enhance", "123.0:abc", "--session", "s1"]), 0)
                ui = pane.load_ui("s1")
            finally:
                coach.STATE = saved
        self.assertIn("123.0:abc", ui["pending"]); self.assertIn("123.0:abc", ui["tried"])

    def test_install_reports_what_happened(self):
        with mock.patch.object(pane.review, "install_skill", return_value=(False, "no draft at x; run the review first")):
            with mock.patch("sys.stdout") as out:
                self.assertEqual(pane.main(["--install", "write-commit"]), 1)
        self.assertIn("no draft", "".join(c.args[0] for c in out.write.call_args_list))

    def test_no_arguments_is_an_error_not_a_crash(self):
        with mock.patch("sys.stdout"):
            self.assertEqual(pane.main([]), 2)


if __name__ == "__main__":
    unittest.main()
