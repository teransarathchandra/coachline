import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach, watch  # noqa: E402

T0 = 1750000000000
VAGUE = "handle this carefully and make it good for all the customers we have"


def history(cfg, rows):
    """rows: (session, project, text); 90 seconds apart."""
    with open(os.path.join(cfg, "history.jsonl"), "w", encoding="utf-8") as f:
        for i, (sid, proj, text) in enumerate(rows):
            f.write(json.dumps({"display": text, "timestamp": str(T0 + i * 90000), "project": proj, "sessionId": sid}) + "\n")


def once(cfg, w=150, h=40):
    env = {**os.environ, "CLAUDE_CONFIG_DIR": cfg, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "watch.py"), "--once", "--width", str(w), "--height", str(h)],
                       capture_output=True, text=True, encoding="utf-8", env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.cfg = self.tmp.name
        self.path = os.path.join(self.cfg, "history.jsonl")
        self._env = os.environ.get("CLAUDE_CONFIG_DIR"); os.environ["CLAUDE_CONFIG_DIR"] = self.cfg

    def tearDown(self):
        self.tmp.cleanup()
        if self._env is None: os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else: os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def drive(self, keys, W=100, H=30):
        """Run the real loop with injected keys; return every frame that was drawn."""
        frames, it = [], iter(keys)
        watch.loop(lambda t: next(it, "q"), lambda rows: frames.append("\n".join(rows)), lambda: (W, H), lambda: watch.build(self.path))
        return frames


class Layout(Base):
    def test_threads_are_columns_and_the_current_one_is_pinned_left(self):
        history(self.cfg, [("a", "D:/work/alpha", VAGUE + " alpha"), ("b", "D:/work/beta", VAGUE + " beta"), ("now", "D:/x/mine", VAGUE + " current")])
        out = once(self.cfg); head = out.splitlines()[1]
        self.assertIn("> THIS THREAD", head)
        self.assertLess(head.index("THIS THREAD"), head.index("beta"))
        self.assertLess(head.index("beta"), head.index("alpha"))     # newest earlier thread first
        self.assertEqual(head.count("│"), 2)                          # three columns, two separators
        self.assertIn("no-vague", out)

    def test_full_text_is_never_truncated(self):
        long = "still not working after the change " + "look at the parser module and " * 8 + "ZEBRA-END"
        history(self.cfg, [("a", "D:/w/alpha", "warm up the thing first please now"), ("a", "D:/w/alpha", long), ("now", "D:/x/mine", VAGUE)])
        self.assertIn("ZEBRA-END", once(self.cfg, 100, 60).replace("│", ""))

    def test_prompt_text_is_redacted(self):
        history(self.cfg, [("now", "p", "mail a.b@example.org the notes carefully and deploy them to the whole site")])
        out = once(self.cfg)
        self.assertNotIn("a.b@example.org", out)
        self.assertIn("<email>", out)

    def test_finished_rewrites_show_in_full(self):
        history(self.cfg, [("now", "p", VAGUE)])
        os.makedirs(os.path.join(self.cfg, "coach"))
        key = coach.prompt_key((float(T0) / 1000, "p", VAGUE))
        with open(os.path.join(self.cfg, "coach", "rewrites.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "text": "AFTER: Goal: make checkout faster.\nDone when: p95 under 300ms.\n\nWHY: adds a done-when."}) + "\n")
        out = once(self.cfg)
        self.assertIn("Goal: make checkout faster.", out)
        self.assertIn("Done when: p95 under 300ms.", out)

    def test_clean_and_empty_history_do_not_crash(self):
        history(self.cfg, [("now", "p", "rename the variable total to grandTotal in cart.js and run the unit tests until they pass")])
        self.assertIn("nothing flagged yet", once(self.cfg))
        os.remove(self.path)
        self.assertIn("no prompts yet", once(self.cfg))

    def test_not_a_terminal_falls_back_to_one_frame(self):
        history(self.cfg, [("now", "p", VAGUE)])
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "watch.py")], capture_output=True, text=True, encoding="utf-8",
                           env=env, stdin=subprocess.DEVNULL, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("THIS THREAD", r.stdout)

    def test_every_frame_fits_the_terminal(self):
        history(self.cfg, [("a", "D:/w/alpha", VAGUE + " a"), ("now", "D:/x/mine", VAGUE + " b")])
        st = watch.build(self.path)
        for W, H in [(24, 8), (40, 12), (60, 20), (61, 20), (100, 30), (200, 60)]:
            lines = watch.render(st, watch.new_ui(), W, H, color=False)
            self.assertLessEqual(len(lines), H - 1, (W, H))
            self.assertTrue(all(len(l) <= max(W, 24) for l in lines), (W, H, [len(l) for l in lines]))


class Navigation(Base):
    def test_arrows_move_focus_and_pan_the_view_sideways(self):
        rows = [(f"s{i}", f"D:/w/p{i}", VAGUE + f" MARK{i}") for i in range(1, 7)] + [("now", "D:/x/mine", VAGUE + " current")]
        history(self.cfg, rows)
        f = self.drive(["right"] * 4 + ["left"] * 3)     # 100 columns wide: the pinned column plus one scrollable column
        self.assertIn("MARK6", f[0])
        self.assertNotIn("MARK3", f[0])                  # the newest earlier thread sits next to the pinned one
        self.assertIn("MARK3", f[4])
        self.assertNotIn("MARK6", f[4])                  # panned three threads to the right
        self.assertIn("current", f[4])                   # the pinned thread never leaves
        self.assertIn("MARK6", f[7])                     # and back again

    def test_vertical_scroll_follows_the_newest_until_you_scroll_up(self):
        history(self.cfg, [("now", "p", VAGUE + f" P{i:02d}") for i in range(1, 13)])
        f = self.drive(["home", "end", "up"], W=100, H=14)
        self.assertIn("P12", f[0])
        self.assertNotIn("P01", f[0])                    # newest visible by default
        self.assertIn("P01", f[1])
        self.assertNotIn("P12", f[1])                    # home: oldest
        self.assertIn("P12", f[2])                       # end: newest again
        self.assertNotEqual(f[2], f[3])                  # up: moved one line

    def test_no_animation_redraws_only_on_a_key_or_new_data(self):
        history(self.cfg, [("now", "p", VAGUE)])
        t, n, writes = [0], [0], []

        def clock():
            t[0] += 3
            return t[0]

        def keys(_timeout):
            n[0] += 1
            return None if n[0] <= 8 else "q"

        watch.loop(keys, lambda rows: writes.append(rows), lambda: (100, 30), lambda: watch.build(self.path), clock=clock)
        self.assertEqual(len(writes), 1)                 # eight idle polls, one draw
        writes.clear(); n[0] = 0; calls = [0]

        def load():
            calls[0] += 1
            if calls[0] > 1: history(self.cfg, [("now", "p", VAGUE), ("now", "p", VAGUE + " a newer prompt")])
            return watch.build(self.path)

        watch.loop(keys, lambda rows: writes.append(rows), lambda: (100, 30), load, clock=clock)
        self.assertEqual(len(writes), 2)                 # new data means exactly one more draw

    @unittest.skipIf(os.name == "nt", "needs a POSIX pty; the Windows msvcrt path is not covered by tests")
    def test_real_keyboard_in_a_pty(self):
        import pty, select, time
        history(self.cfg, [("a", "D:/w/alpha", VAGUE + " earlier"), ("now", "D:/x/mine", VAGUE + " current")])
        pid, fd = pty.fork()
        if pid == 0:  # child: the real watch.py on the pty's slave side
            os.environ.update({"CLAUDE_CONFIG_DIR": self.cfg, "TERM": "xterm", "PYTHONIOENCODING": "utf-8"})
            os.execv(sys.executable, [sys.executable, os.path.join(ROOT, "scripts", "watch.py"), "--width", "100", "--height", "30"])
        buf = ""

        def read_until(marker, timeout=15):
            nonlocal buf
            end = time.time() + timeout
            while marker not in buf and time.time() < end:
                if select.select([fd], [], [], 0.2)[0]:
                    try: buf += os.read(fd, 65536).decode("utf-8", "ignore")
                    except OSError: break
            return marker in buf

        try:
            self.assertTrue(read_until("thread 1 of 2"), buf[-300:])
            self.assertIn("\033[?1049h", buf)                  # alternate screen
            os.write(fd, b"\x1b[C")                            # the right-arrow key, as a terminal sends it
            self.assertTrue(read_until("thread 2 of 2"), buf[-300:])
            os.write(fd, b"q")
            self.assertTrue(read_until("\033[?1049l"), buf[-200:])   # terminal restored on quit
            _, status = os.waitpid(pid, 0)
            self.assertEqual(os.WEXITSTATUS(status), 0)
        finally:
            try: os.kill(pid, 9)
            except OSError: pass

    def test_key_tables_and_quit(self):
        self.assertEqual(watch.POSIX_KEYS["[A"], "up")
        self.assertEqual(watch.POSIX_KEYS["[6~"], "pgdn")
        self.assertEqual(watch.WIN_KEYS["M"], "right")
        history(self.cfg, [("a", "p", VAGUE), ("now", "p", VAGUE)])
        st, ui = watch.build(self.path), watch.new_ui()
        self.assertFalse(watch.handle(ui, st, "l")); self.assertEqual(ui["focus"], 1)
        self.assertFalse(watch.handle(ui, st, "l")); self.assertEqual(ui["focus"], 1)   # clamps at the last thread
        self.assertFalse(watch.handle(ui, st, "h")); self.assertEqual(ui["focus"], 0)
        self.assertTrue(watch.handle(ui, st, "q"))
        self.assertTrue(watch.handle(ui, st, "\x03"))


if __name__ == "__main__":
    unittest.main()
