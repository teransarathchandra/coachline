import json, os, re, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach  # noqa: E402

T0 = 1750000000000
OLD_A = "still not working after the merge, try something else entirely please"
OLD_B = "deploy it to the release environment and revert whatever breaks"
CUR_BAD = "handle this carefully and make it good for all the customers we have"
CUR_OK = "rename the variable total to grandTotal in cart.js and run the unit tests until they pass"
EMAIL = "mail a.b@example.org the release notes and deploy them carefully to the site please"


def history(cfg, rows):
    with open(os.path.join(cfg, "history.jsonl"), "w", encoding="utf-8") as f:
        for i, (sid, text) in enumerate(rows):
            f.write(json.dumps({"display": text, "timestamp": str(T0 + i * 90000), "project": "p", "sessionId": sid}) + "\n")


def frames(cfg, n=3, w=100, h=30):
    env = {**os.environ, "CLAUDE_CONFIG_DIR": cfg, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "watch.py"), "--frames", str(n), "--width", str(w), "--height", str(h)],
                       capture_output=True, text=True, encoding="utf-8", env=env)
    assert r.returncode == 0, r.stderr
    return [p for p in re.split(r"=== frame \d+ ===\n", r.stdout) if p.strip()]


class Watch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.cfg = self.tmp.name
        history(self.cfg, [("old-1", OLD_A), ("old-1", OLD_B), ("old-2", OLD_A + " again"),
                           ("now", CUR_OK), ("now", CUR_BAD)])

    def tearDown(self): self.tmp.cleanup()

    def test_current_thread_is_permanent_and_separate_from_earlier(self):
        fs = frames(self.cfg, 4)
        self.assertEqual(len(fs), 4)
        for f in fs:
            top, bottom = f.split("EARLIER THREADS")
            self.assertIn("THIS THREAD", top)
            self.assertIn("handle this carefully", top)      # the current thread's flagged prompt, every frame
            self.assertIn("no-vague", top)
            self.assertNotIn("still not working", top)       # earlier threads never leak into the permanent panel
            self.assertNotIn("handle this carefully", bottom)

    def test_earlier_threads_scroll_upward_one_line_at_a_time(self):
        f0, f1 = frames(self.cfg, 2)
        e0 = f0.split("EARLIER THREADS")[1].splitlines()[1:]
        e1 = f1.split("EARLIER THREADS")[1].splitlines()[1:]
        self.assertNotEqual(e0, e1)
        self.assertEqual(e1[:6], e0[1:7])  # every line moved up exactly one row

    def test_prompt_text_is_redacted_on_screen(self):
        history(self.cfg, [("old-1", EMAIL), ("now", CUR_BAD)])
        out = "\n".join(frames(self.cfg, 2))
        self.assertNotIn("a.b@example.org", out)
        self.assertIn("<email>", out)

    def test_finished_rewrites_show_as_after(self):
        rows = [("old-1", OLD_A), ("now", CUR_BAD)]; history(self.cfg, rows)
        os.makedirs(os.path.join(self.cfg, "coach"))
        key = coach.prompt_key((float(T0 + 90000) / 1000, "p", CUR_BAD))
        with open(os.path.join(self.cfg, "coach", "rewrites.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "text": "AFTER: Goal: make checkout faster.\nDone when: p95 under 300ms.\n\nWHY: adds a done-when."}) + "\n")
        top = frames(self.cfg, 1)[0].split("EARLIER THREADS")[0]
        self.assertIn("AFTER: Goal: make checkout faster.", top)
        self.assertIn("Done when: p95 under 300ms.", top)

    def test_clean_thread_and_empty_history_do_not_crash(self):
        history(self.cfg, [("old-1", OLD_A), ("now", CUR_OK)])
        self.assertIn("nothing flagged in this thread yet", frames(self.cfg, 1)[0])
        os.remove(os.path.join(self.cfg, "history.jsonl"))
        self.assertIn("no prompts in this thread yet", frames(self.cfg, 1)[0])

    def test_live_loop_uses_the_alternate_screen_redraws_and_restores_the_terminal(self):
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.cfg, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "watch.py"), "--ticks", "4", "--speed", "0.05",
                            "--width", "90", "--height", "24"], capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertTrue(out.startswith("\033[?1049h\033[?25l"))          # alternate screen on, cursor hidden
        self.assertTrue(out.endswith("\033[?25h\033[?1049l"))            # both restored on exit
        self.assertEqual(out.count("\033[H"), 4)                          # one in-place redraw per tick
        self.assertIn("handle this carefully", out)

    def test_render_fits_any_terminal_size(self):
        st = __import__("watch").build(os.path.join(self.cfg, "history.jsonl"))
        w = __import__("watch")
        for W, H in [(30, 10), (60, 12), (120, 50), (10, 5)]:
            lines = w.render(st, W, H, 3, color=False)
            self.assertLessEqual(len(lines), max(H, 10) - 1)
            self.assertTrue(all(len(l) <= max(W, 30) for l in lines), (W, H))


if __name__ == "__main__":
    unittest.main()
