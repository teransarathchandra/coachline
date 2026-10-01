import datetime as dt, json, os, time, unittest

from test_watch import Base, history, once, flat, T0, VAGUE, SOLID
import coach, review, watch


class Fake:
    """Stands in for watch.IO: records the background jobs the panel starts."""
    def __init__(self):
        self.enhanced, self.reviews = [], 0

    def enhance(self, key): self.enhanced.append(key)
    def review(self): self.reviews += 1
    def copy(self, text): return "fake"
    def install(self, slug): return True, "installed " + slug


def key_for(i, text, proj="p"):
    return coach.prompt_key((float(T0 + i * 90000) / 1000, proj, text))


def fresh_learned(days_old=0, history_prompts=100):
    d = (dt.date.today() - dt.timedelta(days=days_old)).isoformat()
    return {"generated": d, "prompts": 100, "history_prompts": history_prompts, "requests": [], "mistakes": []}


class Autopilot(Base):
    def setUp(self):
        super().setUp()
        self.texts = [VAGUE + f" N{i}" for i in range(7)]
        history(self.cfg, [("now", "p", t) for t in self.texts])
        self.io = Fake(); self.ui = watch.new_ui()

    def on(self):
        self.write_json("config.json", {"panel_ai": True})
        self.write_json("learned.json", fresh_learned())          # a recent review exists, so only prompt analysis is in play
        return watch.build(self.path)

    def test_it_does_nothing_when_claude_analysis_is_off(self):
        st = watch.build(self.path)
        self.assertEqual(watch.autopilot(st, self.ui, self.io), [])
        self.assertEqual((self.io.enhanced, self.io.reviews), ([], 0))

    def test_it_analyses_the_newest_unanalysed_prompt_one_at_a_time(self):
        st = self.on()
        acts = watch.autopilot(st, self.ui, self.io)
        self.assertEqual(acts, [("enhance", key_for(6, self.texts[6]))])               # the newest, not the oldest
        self.assertEqual(watch.autopilot(st, self.ui, self.io), [])                    # one in flight: wait for it
        self.assertIn(key_for(6, self.texts[6]), self.ui["pending"])

    def test_after_it_finishes_the_next_newest_is_taken_but_only_among_the_last_five(self):
        st = self.on()
        for n in range(8):
            self.ui["pending"] = {}                                                      # pretend each job finished
            watch.autopilot(st, self.ui, self.io)
        self.assertEqual(self.io.enhanced, [key_for(i, self.texts[i]) for i in (6, 5, 4, 3, 2)])   # five, newest first, then stop
        self.assertEqual(len(set(self.io.enhanced)), 5)                                 # never the same prompt twice

    def test_analysed_failed_and_opted_out_prompts_are_skipped(self):
        st = self.on()
        os.makedirs(self.state_dir(), exist_ok=True)
        with open(os.path.join(self.state_dir(), "rewrites.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"key": key_for(6, self.texts[6]), "text": "AFTER: x", "advice": {"after": "x", "task": "t"}}) + "\n")   # analysed
            f.write(json.dumps({"key": key_for(5, self.texts[5]), "error": "boom"}) + "\n")                                               # failed
        history(self.cfg, [("now", "p", t) for t in self.texts[:4]] + [("now", "D:/w/secret", self.texts[4]), ("now", "p", self.texts[5]), ("now", "p", self.texts[6])])
        with open(os.path.join(self.state_dir(), "llm-off.txt"), "w") as f: f.write("secret\n")
        st = watch.build(self.path)
        acts = watch.autopilot(st, self.ui, self.io)
        self.assertEqual(acts, [("enhance", key_for(3, self.texts[3]))])                # 6 analysed, 5 failed, 4 opted out

    def test_one_liners_are_not_worth_a_call(self):
        self.write_json("config.json", {"panel_ai": True}); self.write_json("learned.json", fresh_learned())
        history(self.cfg, [("now", "p", "continue"), ("now", "p", "rename x to y")])
        self.assertEqual(watch.autopilot(watch.build(self.path), self.ui, self.io), [])

    def test_the_history_review_starts_when_none_exists_and_never_twice_in_half_an_hour(self):
        self.write_json("config.json", {"panel_ai": True})
        st = watch.build(self.path); now = time.time()
        self.assertIn(("review",), watch.autopilot(st, self.ui, self.io, now))
        self.assertNotIn(("review",), watch.autopilot(st, self.ui, self.io, now + 60))
        self.assertIn(("review",), watch.autopilot(st, self.ui, self.io, now + 1801))
        self.assertEqual(self.io.reviews, 2)

    def test_it_waits_while_a_review_is_already_running(self):
        self.write_json("config.json", {"panel_ai": True})
        with open(os.path.join(self.state_dir(), "review.running"), "w") as f: f.write("x")
        self.assertNotIn(("review",), watch.autopilot(watch.build(self.path), self.ui, self.io))

    def test_review_due_rules(self):
        now = time.time(); orig = review.count_prompts
        try:
            review.count_prompts = lambda path: 130
            st = {"review_running": False, "learned": fresh_learned(days_old=1, history_prompts=100)}
            self.assertFalse(watch.review_due(st, now))                                   # reviewed yesterday: not due
            st["learned"] = fresh_learned(days_old=3, history_prompts=100)
            self.assertTrue(watch.review_due(st, now))                                    # 3 days old and 30 new prompts
            st["learned"] = fresh_learned(days_old=3, history_prompts=120)
            self.assertFalse(watch.review_due(st, now))                                   # old, but only 10 new prompts
            st["learned"] = {"generated": "not a date"}
            self.assertTrue(watch.review_due(st, now))
            st["review_running"] = True
            self.assertFalse(watch.review_due(st, now))
        finally:
            review.count_prompts = orig

    def test_the_loop_runs_the_autopilot_at_start_and_when_new_data_arrives(self):
        self.on()
        t, n = [0], [0]

        def clock():
            t[0] += 3
            return t[0]

        def keys(_timeout):
            n[0] += 1
            return None if n[0] <= 4 else "q"

        calls = []
        watch.loop(keys, lambda rows: None, lambda: (100, 30), lambda: watch.build(self.path), clock=clock, io=self.io,
                   work=lambda st, ui: calls.append(watch.autopilot(st, ui, self.io, now=1000.0 + len(calls))))
        self.assertGreaterEqual(len(calls), 2)                                           # at start and on reload ticks
        self.assertEqual(len(self.io.enhanced), 1)                                       # but one analysis is in flight, not one per tick


class EndToEnd(Base):
    def test_panel_status_and_switch_round_trip(self):
        history(self.cfg, [("now", "p", VAGUE)])
        self.assertFalse(coach.ai_on())
        coach.set_setting("auto_rewrite", True)                                           # the old name still works
        self.assertTrue(coach.ai_on())
        coach.set_setting("panel_ai", False)                                              # the new name wins
        self.assertFalse(coach.ai_on())
        self.assertIn("Claude off", flat(once(self.cfg)))


class NoWindow(unittest.TestCase):
    """On Windows a console program started by a job without a console opens its own visible window. The panel's background
    jobs must own a hidden console instead (CREATE_NO_WINDOW without DETACHED_PROCESS, which makes Windows ignore it)."""

    def test_background_jobs_and_claude_calls_never_open_a_window(self):
        from unittest import mock
        seen = []
        with mock.patch.object(coach.subprocess, "Popen", lambda argv, **kw: seen.append(kw)):
            coach.spawn_key("k"); coach.spawn_review()
        self.assertEqual(len(seen), 2)
        if os.name == "nt":
            for kw in seen:
                self.assertTrue(kw["creationflags"] & 0x08000000)          # CREATE_NO_WINDOW
                self.assertFalse(kw["creationflags"] & 0x00000008)         # not DETACHED_PROCESS
            self.assertEqual(coach.NO_WINDOW, {"creationflags": 0x08000000})   # also passed to `claude -p` and the clipboard helpers
        else:
            self.assertTrue(all(kw.get("start_new_session") for kw in seen))


if __name__ == "__main__":
    unittest.main()
