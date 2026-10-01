import json, os, re, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach, watch  # noqa: E402

T0 = 1750000000000
VAGUE = "handle this carefully and make it good for all the customers we have"
SOLID = ("please look at the invoice module and rework how it calculates the tax for every region because the current approach "
         "is hard to extend and the team finds it hard to read and maintain over time and verify the totals afterwards")


def history(cfg, rows):
    """rows: (session, project, text); 90 seconds apart."""
    with open(os.path.join(cfg, "history.jsonl"), "w", encoding="utf-8") as f:
        for i, (sid, proj, text) in enumerate(rows):
            f.write(json.dumps({"display": text, "timestamp": str(T0 + i * 90000), "project": proj, "sessionId": sid}) + "\n")


def once(cfg, w=100, h=40):
    env = {**os.environ, "CLAUDE_CONFIG_DIR": cfg, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "watch.py"), "--once", "--width", str(w), "--height", str(h)],
                       capture_output=True, text=True, encoding="utf-8", env=env, input="")
    assert r.returncode == 0, r.stderr
    return r.stdout


def flat(s):
    return " ".join(re.sub(r"\x1b\[[0-9;]*m", "", s).split())


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.cfg = self.tmp.name
        self.path = os.path.join(self.cfg, "history.jsonl")
        self._env = os.environ.get("CLAUDE_CONFIG_DIR"); os.environ["CLAUDE_CONFIG_DIR"] = self.cfg
        # coach.py fixes its paths when it is imported. In-process tests must not read or write the real ~/.claude/coach.
        self._paths = {n: getattr(coach, n) for n in ("CONFIG", "HIST", "STATE", "REWRITES", "OFF", "ALIVE", "USER_CFG", "REVIEW_LOCK", "LEARNED")}
        st = os.path.join(self.cfg, "coach")
        coach.CONFIG, coach.HIST, coach.STATE = self.cfg, self.path, st
        coach.REWRITES, coach.OFF, coach.ALIVE = (os.path.join(st, n) for n in ("rewrites.jsonl", "llm-off.txt", "watch.alive"))
        coach.USER_CFG, coach.REVIEW_LOCK, coach.LEARNED = (os.path.join(st, n) for n in ("config.json", "review.running", "learned.json"))

    def tearDown(self):
        for n, v in self._paths.items(): setattr(coach, n, v)
        self.tmp.cleanup()
        if self._env is None: os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else: os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def state_dir(self):
        os.makedirs(os.path.join(self.cfg, "coach"), exist_ok=True)
        return os.path.join(self.cfg, "coach")

    def write_json(self, name, data):
        with open(os.path.join(self.state_dir(), name), "w", encoding="utf-8") as f: json.dump(data, f)

    def drive(self, keys, W=100, H=30, io=None, work=None):
        """Run the real loop with injected keys; return every frame that was drawn."""
        frames, it = [], iter(keys)
        watch.loop(lambda t: next(it, "q"), lambda rows: frames.append("\n".join(rows)), lambda: (W, H), lambda: watch.build(self.path), io=io, work=work)
        return frames


class Scope(Base):
    def test_only_this_thread_is_shown_and_in_one_column(self):
        history(self.cfg, [("old", "p", "OLDONE " + VAGUE), ("old", "p", "OLDTWO " + VAGUE), ("now", "p", "NOWONE " + VAGUE), ("now", "p", "NOWTWO " + VAGUE)])
        out = once(self.cfg)
        self.assertIn("this thread", out)
        self.assertIn("NOWONE", out); self.assertIn("NOWTWO", out)
        self.assertNotIn("OLDONE", out); self.assertNotIn("OLDTWO", out)    # earlier threads are not displayed
        self.assertNotIn("\u2502", out)                                      # a single column: no separators

    def test_every_prompt_of_this_thread_is_listed_even_if_it_passed_every_rule(self):
        history(self.cfg, [("now", "p", SOLID), ("now", "p", VAGUE)])
        out = flat(once(self.cfg))
        self.assertIn("rework how it calculates the tax", out)
        self.assertIn("handle this carefully", out)

    def test_text_is_never_truncated_and_secrets_are_redacted(self):
        long = "still not working after the change " + "look at the parser module and " * 8 + "ZEBRA-END"
        history(self.cfg, [("now", "p", long), ("now", "p", "mail a.b@example.org the notes and password=hunter2 to the whole site carefully")])
        out = once(self.cfg, 60, 60)
        self.assertIn("ZEBRA-END", flat(out))
        self.assertNotIn("a.b@example.org", out); self.assertNotIn("hunter2", out)
        self.assertIn("<email>", out)

    def test_clean_and_empty_history_do_not_crash(self):
        history(self.cfg, [("now", "p", "continue")])
        self.assertIn("no prompts in this thread yet", once(self.cfg))
        os.remove(self.path)
        self.assertIn("no prompts in this thread yet", once(self.cfg))

    def test_not_a_terminal_falls_back_to_one_frame(self):
        history(self.cfg, [("now", "p", VAGUE)])
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "watch.py")], capture_output=True, text=True, encoding="utf-8",
                           env=env, stdin=subprocess.DEVNULL, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("this thread", r.stdout)

    def test_every_frame_fits_the_terminal(self):
        history(self.cfg, [("old", "p", VAGUE + " a"), ("now", "p", VAGUE + " b"), ("now", "p", SOLID)])
        self.write_json("learned.json", {"generated": "2026-09-30", "prompts": 99, "requests": [{"name": "carefully-things", "keywords": ["carefully"], "count": 4}], "mistakes": []})
        st = watch.build(self.path)
        for W, H in [(30, 10), (45, 14), (60, 20), (100, 30), (200, 60)]:
            lines = watch.render(st, watch.new_ui(), W, H, color=False)
            self.assertLessEqual(len(lines), H - 1, (W, H))
            self.assertTrue(all(len(l) <= max(W, 30) for l in lines), (W, H, [len(l) for l in lines if len(l) > max(W, 30)]))


class Colours(Base):
    def test_your_prompt_is_white_and_what_can_be_improved_is_blue(self):
        history(self.cfg, [("now", "p", "UNIQUEPROMPT " + VAGUE)])
        rows = watch.render(watch.build(self.path), watch.new_ui(), 100, 30, color=True)
        prompt = next(r for r in rows if "UNIQUEPROMPT" in r)
        self.assertTrue(prompt.startswith("\x1b[1;97m"), repr(prompt[:20]))              # bright white
        head = next(r for r in rows if "can be improved:" in r)
        self.assertTrue(head.startswith("\x1b[1;94m"), repr(head[:20]))                  # bright blue
        hint = next(r for r in rows if "no-vague" in r)
        self.assertTrue(hint.startswith("\x1b[94m"), repr(hint[:20]))
        self.assertNotIn("97", head[:8]); self.assertNotIn("94", prompt[:8])

    def test_claudes_advice_and_the_enhanced_prompt_are_blue_too(self):
        history(self.cfg, [("now", "p", VAGUE)])
        key = coach.prompt_key((float(T0) / 1000, "p", VAGUE))
        self.write_json("rewrites.jsonl", {})
        with open(os.path.join(self.state_dir(), "rewrites.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "text": "AFTER: x", "advice": {"task": "backend", "summary": "checkout", "use": [], "get": [], "tips": ["Give a number."],
                                                                              "workflow": [], "after": "ENHANCEDLINE make checkout faster"}}) + "\n")
        rows = watch.render(watch.build(self.path), watch.new_ui(), 100, 40, color=True)
        for needle in ("task: backend", "tip: Give a number.", "ENHANCEDLINE"):
            r = next(x for x in rows if needle in x)
            self.assertIn("\x1b[1;94m" if needle.startswith("task") else "\x1b[94m", r[:12], needle)


class FromYourPastChats(Base):
    def setUp(self):
        super().setUp()
        history(self.cfg, [("old1", "p", "write a commit message for the staged change please"), ("old2", "p", "give me a commit message for this diff"),
                           ("old3", "p", "need a commit message again for the next change"), ("now", "p", "one more commit message for the checkout change please")])

    def learned(self, **extra):
        self.write_json("learned.json", {"generated": "2026-09-30", "prompts": 120, "history_prompts": 120,
                                         "requests": [{"name": "commit-message", "keywords": ["commit message"], "count": 4}],
                                         "mistakes": [{"name": "no-reason-correction", "keywords": ["still broken"], "fix": "say which rule it broke"}], **extra})

    def test_a_request_you_repeat_in_past_chats_and_in_this_thread_suggests_a_skill(self):
        self.learned()
        out = flat(once(self.cfg))
        self.assertIn('You have asked for "commit-message" 3x in past chats and 1x in this thread', out)
        self.assertIn("make it a skill, /commit-message", out)

    def test_a_drafted_skill_can_be_installed_with_s_and_is_then_recognised(self):
        self.learned()
        d = os.path.join(self.state_dir(), "drafts", "commit-message"); os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w") as f: f.write("---\nname: commit-message\ndescription: x\n---\nsteps\n")
        self.assertIn("a draft is ready: press s to install it", flat(once(self.cfg)))

        class IO:
            def install(self, slug):
                import review
                return review.install_skill(slug)
        f = self.drive(["s"], io=IO())
        self.assertIn("installed", f[1])
        self.assertTrue(os.path.isfile(os.path.join(self.cfg, "skills", "commit-message", "SKILL.md")))
        self.assertIn("you already have /commit-message: use it", flat(once(self.cfg)))   # no second offer

    def test_s_without_a_draft_says_so(self):
        self.learned()
        self.assertIn("no drafted skill to install yet", self.drive(["s"])[1])

    def test_a_recurring_mistake_shows_only_when_this_thread_repeats_it(self):
        self.learned()
        self.assertNotIn("Recurring gap", flat(once(self.cfg)))
        history(self.cfg, [("old1", "p", "still broken after the first try please fix it again"), ("old2", "p", "it is still broken after the second try as well"),
                           ("now", "p", "now it is still broken after the third try and I am stuck")])
        self.assertIn("Recurring gap (2x before, 1x here), no-reason-correction: say which rule it broke", flat(once(self.cfg)))

    def test_nothing_is_shown_when_no_history_pattern_matches_this_thread(self):
        self.learned()
        history(self.cfg, [("old1", "p", "write a commit message for this"), ("now", "p", "explain how the invoice cache works in detail")])
        out = flat(once(self.cfg))
        self.assertNotIn("commit-message", out)
        self.assertIn("nothing you repeated in past chats shows up in this thread yet", out)

    def test_the_status_line_says_what_claude_has_done(self):
        out = flat(once(self.cfg))
        self.assertIn("Claude analysis is OFF. Turn it on:", out)
        self.assertIn("setup.py --panel-ai on", out)
        self.write_json("config.json", {"panel_ai": True})
        self.assertIn("Claude will analyse your past chats in the background", flat(once(self.cfg)))
        self.learned()
        self.assertIn("Claude analysed 120 prompts from your past chats on 2026-09-30", flat(once(self.cfg)))
        with open(os.path.join(self.state_dir(), "review.running"), "w") as f: f.write("x")
        self.assertIn("Claude is analysing your past chats right now", flat(once(self.cfg)))


class Analysis(Base):
    def test_finished_analysis_shows_improvements_and_the_enhanced_prompt_for_any_prompt(self):
        history(self.cfg, [("now", "p", SOLID)])                                          # passed every rule: still analysed
        key = coach.prompt_key((float(T0) / 1000, "p", SOLID))
        advice = {"task": "refactoring", "summary": "tax rework", "use": [{"name": "simplify", "why": "clean up after"}], "get": [{"name": "shiny@mk", "why": "codemods"}],
                  "tips": ["Ask for every usage first."], "workflow": ["Search", "Rename", "Test"], "after": "Rework the tax code.\nDone when: tests pass."}
        os.makedirs(self.state_dir(), exist_ok=True)
        with open(os.path.join(self.state_dir(), "rewrites.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "text": "AFTER: x", "advice": advice, "discovery": [{"name": "GreatKit", "kind": "tool", "why": "better", "url": "https://x.example.com/g",
                                                                                                   "install": "npm i g", "stars": 1200, "pushed": "2026-08-01"}]}) + "\n")
        out = flat(once(self.cfg, 120, 60))
        for want in ("can be improved:", "task: refactoring", "use: /simplify", "get: /plugin install shiny@mk", "tip: Ask for every usage first.",
                     "flow: 1) Search 2) Rename 3) Test", "enhanced prompt (press c to copy):", "Rework the tax code.", "Done when: tests pass.",
                     "web-found, not installed", "better: GreatKit (tool)"):
            self.assertIn(want, out)

    def test_a_failed_analysis_says_why_and_how_to_retry(self):
        history(self.cfg, [("now", "p", VAGUE)])
        key = coach.prompt_key((float(T0) / 1000, "p", VAGUE))
        os.makedirs(self.state_dir(), exist_ok=True)
        with open(os.path.join(self.state_dir(), "rewrites.jsonl"), "w", encoding="utf-8") as f: f.write(json.dumps({"key": key, "error": "boom"}) + "\n")
        self.assertIn("Claude's analysis failed (boom). Press e to try again.", flat(once(self.cfg)))


class Navigation(Base):
    def setUp(self):
        super().setUp()
        history(self.cfg, [("now", "p", VAGUE + f" P{i:02d}") for i in range(1, 13)])

    def marked(self, frame):
        lines = re.sub(r"\x1b\[[0-9;]*m", "", frame).splitlines(); n = next(i for i, l in enumerate(lines) if "* " in l and re.search(r"\d\d:\d\d", l))
        return " ".join(lines[n + 1:n + 3])

    def test_n_and_p_move_the_marker_and_scroll_it_into_view(self):
        f = self.drive(["p"] * 11, W=100, H=16)
        self.assertIn("P12", self.marked(f[0]))
        self.assertNotIn("P01", f[0])                                   # the oldest is off screen at first
        self.assertIn("P01", self.marked(f[-1]))                        # and visible once selected
        f = self.drive(["p", "p", "n"])
        self.assertIn("P11", self.marked(f[1])); self.assertIn("P10", self.marked(f[2])); self.assertIn("P11", self.marked(f[3]))

    def test_scrolling_up_stops_following_and_g_capital_resumes(self):
        f = self.drive(["home", "end", "up"], W=100, H=16)
        self.assertNotIn("P12", f[1]); self.assertIn("P01", f[1])
        self.assertIn("P12", f[2])
        self.assertNotEqual(f[2], f[3])

    def test_no_animation_redraws_only_on_a_key_or_new_data(self):
        t, n, writes = [0], [0], []

        def clock():
            t[0] += 3
            return t[0]

        def keys(_timeout):
            n[0] += 1
            return None if n[0] <= 8 else "q"

        watch.loop(keys, lambda rows: writes.append(rows), lambda: (100, 30), lambda: watch.build(self.path), clock=clock)
        self.assertEqual(len(writes), 1)                                # eight idle polls, one draw
        writes.clear(); n[0] = 0; calls = [0]

        def load():
            calls[0] += 1
            if calls[0] > 1: history(self.cfg, [("now", "p", VAGUE + f" P{i:02d}") for i in range(1, 14)])
            return watch.build(self.path)

        watch.loop(keys, lambda rows: writes.append(rows), lambda: (100, 30), load, clock=clock)
        self.assertEqual(len(writes), 2)                                # new data means exactly one more draw

    def test_detail_view_and_the_key_tables(self):
        f = self.drive(["enter", "esc"], W=100, H=24)
        self.assertIn("YOUR PROMPT", f[1]); self.assertIn("CAN BE IMPROVED", f[1]); self.assertIn("ENHANCED PROMPT", f[1])
        self.assertNotIn("YOUR PROMPT", f[2])
        self.assertEqual(watch.POSIX_KEYS["[A"], "up"); self.assertEqual(watch.WIN_KEYS["P"], "down")
        self.assertEqual((watch.ALIASES["\r"], watch.ALIASES["\x1b"], watch.ALIASES["c"], watch.ALIASES["e"], watch.ALIASES["s"]), ("enter", "esc", "copy", "enhance", "skill"))
        ui, st = watch.new_ui(), watch.build(self.path)
        self.assertFalse(watch.handle(ui, st, "j")); self.assertTrue(watch.handle(ui, st, "q")); self.assertTrue(watch.handle(ui, st, "\x03"))

    @unittest.skipIf(os.name == "nt", "needs a POSIX pty; the Windows msvcrt path is not covered by tests")
    def test_real_keyboard_in_a_pty(self):
        import pty, select, time
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
            self.assertTrue(read_until("this thread"), buf[-300:])
            self.assertIn("\033[?1049h", buf)                  # alternate screen
            os.write(fd, b"c")                                 # copy with no enhanced prompt yet: a message, proving the key was read
            self.assertTrue(read_until("no enhanced prompt yet"), buf[-300:])
            os.write(fd, b"q")
            self.assertTrue(read_until("\033[?1049l"), buf[-200:])   # terminal restored on quit
            _, status = os.waitpid(pid, 0)
            self.assertEqual(os.WEXITSTATUS(status), 0)
        finally:
            try: os.kill(pid, 9)
            except OSError: pass


if __name__ == "__main__":
    unittest.main()
