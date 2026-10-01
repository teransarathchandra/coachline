import json, os, re, subprocess, sys, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach, watch  # noqa: E402

T0 = 1750000000000
VAGUE = "handle this carefully and make it good for all the customers we have"
SOLID = ("please look at the invoice module and rework how it calculates the tax for every region because the current approach "
         "is hard to extend and the team finds it hard to read and maintain over time and verify the totals afterwards")
ADVICE = {"task": "refactoring", "summary": "tax rework", "use": [{"name": "simplify", "why": "clean up after"}], "get": [{"name": "shiny@mk", "why": "codemods"}],
          "tips": ["Ask for every usage first.", "Name the files that must not change."], "workflow": ["Search", "Rename", "Test"],
          "after": "Rework the tax code in the invoice module.\nDone when: the unit tests pass."}


def history(cfg, rows):
    """rows: (session, project, text); 90 seconds apart."""
    with open(os.path.join(cfg, "history.jsonl"), "w", encoding="utf-8") as f:
        for i, (sid, proj, text) in enumerate(rows):
            f.write(json.dumps({"display": text, "timestamp": str(T0 + i * 90000), "project": proj, "sessionId": sid}) + "\n")


def key_for(i, text, proj="p"):
    return coach.prompt_key((float(T0 + i * 90000) / 1000, proj, text))


def once(cfg, w=100, h=40, *extra):
    env = {**os.environ, "CLAUDE_CONFIG_DIR": cfg, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "watch.py"), "--once", "--width", str(w), "--height", str(h), *extra],
                       capture_output=True, text=True, encoding="utf-8", env=env, input="")
    assert r.returncode == 0, r.stderr
    return r.stdout


def plain(s):
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def flat(s):
    return " ".join(plain(s).split())


def card_of(frame):
    """The text between the first and second rule: the card for the selected prompt."""
    lines = plain(frame).splitlines()
    rules = [n for n, l in enumerate(lines) if l.strip().startswith("\u2500")]
    return " ".join(" ".join(lines[rules[0] + 1:rules[1]]).split())


def list_of(frame):
    lines = plain(frame).splitlines()
    start = next(n for n, l in enumerate(lines) if "Prompts in this thread" in l)
    return lines[start + 1:-1]


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

    def add_record(self, key, **rec):
        with open(os.path.join(self.state_dir(), "rewrites.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"key": key, **rec}) + "\n")

    def analyse(self, i, text, advice=ADVICE, **extra):
        self.add_record(key_for(i, text), text="AFTER: " + advice["after"], advice=advice, **extra)

    def drive(self, keys, W=100, H=30, io=None, work=None):
        """Run the real loop with injected keys; return every frame that was drawn."""
        frames, it = [], iter(keys)
        watch.loop(lambda t: next(it, "q"), lambda rows: frames.append("\n".join(rows)), lambda: (W, H), lambda: watch.build(self.path), io=io, work=work)
        return frames


class Scope(Base):
    def test_only_this_thread_is_shown(self):
        history(self.cfg, [("old", "p", "OLDONE " + VAGUE), ("old", "p", "OLDTWO " + VAGUE), ("now", "p", "NOWONE " + VAGUE), ("now", "p", "NOWTWO " + VAGUE)])
        out = once(self.cfg)
        self.assertIn("this thread \u00b7 2 prompts", out)
        self.assertIn("NOWONE", out); self.assertIn("NOWTWO", out)
        self.assertNotIn("OLDONE", out); self.assertNotIn("OLDTWO", out)    # earlier threads are never displayed

    def test_every_prompt_of_this_thread_is_in_the_list_even_one_that_passed_every_rule(self):
        history(self.cfg, [("now", "p", SOLID), ("now", "p", VAGUE)])
        out = once(self.cfg)
        rows = list_of(out)
        self.assertEqual(len(rows), 2)
        self.assertIn("rework how it calculates", rows[0]); self.assertIn("handle this carefully", rows[1])

    def test_secrets_are_redacted_everywhere(self):
        history(self.cfg, [("now", "p", "mail a.b@example.org the notes and password=hunter2 to the whole site carefully")])
        out = once(self.cfg)
        self.assertNotIn("a.b@example.org", out); self.assertNotIn("hunter2", out)
        self.assertIn("<email>", out)

    def test_empty_and_one_liner_histories_do_not_crash(self):
        history(self.cfg, [("now", "p", "continue")])
        self.assertIn("No prompts in this thread yet.", once(self.cfg))
        os.remove(self.path)
        self.assertIn("No prompts in this thread yet.", once(self.cfg))

    def test_not_a_terminal_falls_back_to_one_frame(self):
        history(self.cfg, [("now", "p", VAGUE)])
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "watch.py")], capture_output=True, text=True, encoding="utf-8",
                           env=env, stdin=subprocess.DEVNULL, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("this thread", r.stdout)

    def test_every_frame_fits_every_pane_size(self):
        history(self.cfg, [("old", "p", VAGUE + " a")] + [("now", "p", f"N{i} " + VAGUE) for i in range(12)])
        self.analyse(11, "N11 " + VAGUE)
        self.write_json("learned.json", {"generated": "2026-09-30", "prompts": 99, "requests": [{"name": "carefully-things", "keywords": ["carefully"], "count": 4}], "mistakes": []})
        for patterns in (False, True):
            for W, H in [(30, 10), (40, 14), (44, 22), (56, 34), (90, 40), (120, 50), (200, 60)]:
                st = watch.build(self.path); ui = watch.new_ui(); ui["patterns"] = patterns
                lines = watch.render(st, ui, W, H, color=False)
                self.assertLessEqual(len(lines), H - 1, (W, H))
                self.assertTrue(all(len(l) <= max(W, 30) for l in lines), (W, H, [len(l) for l in lines if len(l) > max(W, 30)]))


class TheCard(Base):
    def setUp(self):
        super().setUp()
        history(self.cfg, [("now", "p", f"P{i:02d} " + VAGUE) for i in range(1, 13)])

    def test_the_newest_prompt_is_what_you_see_first_not_a_scrolled_tail(self):
        out = once(self.cfg, 56, 34)
        card = card_of(out)
        self.assertIn("P12", card)                                           # the newest prompt is in the card...
        self.assertNotIn("P05", card)                                        # ...and older ones only in the list
        lines = plain(out).splitlines()
        self.assertTrue(re.search(r"\d\d:\d\d\s+\u00b7", lines[2]), lines[2])    # the very first card line says when, and the state
        self.assertIn("P12", lines[3])                                       # and the prompt text follows immediately

    def test_the_enhanced_prompt_is_visible_in_panes_that_can_hold_it(self):
        self.analyse(11, "P12 " + VAGUE)
        for W, H in [(56, 34), (70, 26), (90, 40), (120, 50)]:
            card = card_of(once(self.cfg, W, H))
            self.assertIn("Enhanced prompt", card, (W, H)); self.assertIn("c to copy", card, (W, H))
            self.assertIn("Done when: the unit tests pass.", card, (W, H))           # the whole thing, not just its first line

    def test_a_short_pane_shrinks_the_improvements_before_the_enhanced_prompt(self):
        self.analyse(11, "P12 " + VAGUE)
        full = card_of(once(self.cfg, 90, 40))
        self.assertIn("get shiny@mk", full); self.assertIn("tax rework", full)       # roomy: task chip, tips, use, get
        small = card_of(once(self.cfg, 70, 21))
        self.assertIn("Enhanced prompt", small)                                      # tight: still there
        self.assertNotIn("get shiny@mk", small)                                      # but the extras are dropped first

    def test_long_prompts_are_cut_in_the_card_and_complete_in_the_full_view(self):
        long = "still not working after the change " + "look at the parser module and " * 8 + "ZEBRA-END"
        history(self.cfg, [("now", "p", long)])
        self.assertNotIn("ZEBRA-END", card_of(once(self.cfg, 56, 34)))
        self.assertIn("Enter shows the whole prompt", card_of(once(self.cfg, 56, 34)))
        f = self.drive(["enter"], W=56, H=34)
        self.assertIn("ZEBRA-END", flat(f[1]))

    def test_the_list_is_compact_with_a_glyph_per_state(self):
        texts = [f"P{i:02d} " + VAGUE for i in range(1, 13)]
        self.analyse(11, texts[11])                                                  # analysed
        self.add_record(key_for(10, texts[10]), error="boom")                        # failed
        with open(os.path.join(self.state_dir(), "llm-off.txt"), "w") as f: f.write("secret\n")
        history(self.cfg, [("now", "p", t) for t in texts[:9]] + [("now", "D:/w/secret", texts[9]), ("now", "p", texts[10]), ("now", "p", texts[11])])
        rows = list_of(once(self.cfg, 100, 60))
        by = {re.search(r"P\d\d", r).group(0): r for r in rows}
        self.assertIn("\u2713", by["P12"]); self.assertIn("\u00d7", by["P11"]); self.assertIn("\u2013", by["P10"])
        self.assertIn("!", by["P01"])                                                 # AI off: a local hint is available

    def test_each_row_of_the_list_is_one_line_however_long_the_prompt(self):
        history(self.cfg, [("now", "p", "word " * 80)] + [("now", "p", VAGUE)])
        rows = list_of(once(self.cfg, 50, 30))
        self.assertTrue(all(len(r) <= 49 for r in rows))
        self.assertTrue(any("\u2026" in r for r in rows))                              # clipped with an ellipsis, not wrapped


class Colours(Base):
    def setUp(self):
        super().setUp()
        history(self.cfg, [("now", "p", "UNIQUEPROMPT " + VAGUE)])

    def rows(self, **kw):
        ui = watch.new_ui(); ui.update(kw)
        return watch.render(watch.build(self.path), ui, 100, 40, color=True)

    def test_your_prompt_is_white_and_what_can_be_improved_is_blue(self):
        rows = self.rows()
        prompt = next(r for r in rows if "UNIQUEPROMPT" in r and "\u203a" not in r)
        self.assertTrue(prompt.startswith("\x1b[1;97m"), repr(prompt[:20]))              # bright white
        label = next(r for r in rows if "Improve" in r)
        self.assertTrue(label.startswith("\x1b[1;94m"), repr(label[:20]))                # bright blue
        hint = next(r for r in rows if "swap 'carefully" in r or "carefully/best/clean" in r)
        self.assertTrue(hint.startswith("\x1b[94m"), repr(hint[:20]))

    def test_claudes_advice_and_the_enhanced_prompt_are_blue_too(self):
        self.analyse(0, "UNIQUEPROMPT " + VAGUE)
        rows = self.rows()
        for needle in ("Ask for every usage first.", "Rework the tax code"):
            self.assertTrue(next(r for r in rows if needle in r).startswith("\x1b[94m"), needle)

    def test_structure_is_grey_and_the_selected_row_is_marked_even_without_colour(self):
        rows = self.rows()
        self.assertTrue(rows[1].startswith("\x1b[90m"))                                  # rules are grey
        sel = next(r for r in rows if "\u203a" in r)
        self.assertTrue(sel.startswith("\x1b[7m"))                                       # reverse video...
        self.assertIn("\u203a", plain(sel))                                              # ...and a marker, for terminals without it

    def test_the_header_dot_shows_whether_claude_is_on(self):
        off = self.rows()[0]
        self.assertIn("\x1b[90m\u25cb Claude off", off)
        self.write_json("config.json", {"panel_ai": True})
        self.analyse(0, "UNIQUEPROMPT " + VAGUE)
        self.assertIn("\x1b[92m\u25cf Claude on", self.rows()[0])
        history(self.cfg, [("now", "p", "UNIQUEPROMPT " + VAGUE), ("now", "p", VAGUE + " newer one")])
        self.assertIn("\x1b[93m\u25cf Claude working", self.rows()[0])                     # a recent prompt is queued


class Status(Base):
    def test_old_prompts_are_never_queued_so_the_header_does_not_spin_forever(self):
        self.write_json("config.json", {"panel_ai": True})
        texts = [f"P{i:02d} " + VAGUE for i in range(1, 9)]
        history(self.cfg, [("now", "p", t) for t in texts])
        for i in range(3, 8): self.analyse(i, texts[i])                                  # the five newest are analysed
        out = once(self.cfg, 100, 40)
        self.assertIn("Claude on", out); self.assertNotIn("working", out)                # the three older ones are not "queued"
        rows = list_of(out)
        self.assertTrue(all("\u2026" not in r.split("P0")[0] for r in rows))

    def test_a_prompt_that_was_started_but_never_answered_says_so(self):
        self.write_json("config.json", {"panel_ai": True})
        history(self.cfg, [("now", "p", VAGUE)])
        st = watch.build(self.path); ui = watch.new_ui(); ui["tried"].add(st["entries"][0]["key"])
        frame = "\n".join(watch.render(st, ui, 90, 30, color=False))
        self.assertIn("no answer yet, press e to retry", frame)
        self.assertNotIn("Claude working", frame)

    def test_a_failed_analysis_says_why_and_how_to_retry(self):
        history(self.cfg, [("now", "p", VAGUE)])
        self.add_record(key_for(0, VAGUE), error="boom")
        self.assertIn("Claude's analysis failed (boom). Press e to try again.", card_of(once(self.cfg)))

    def test_without_claude_the_card_gives_local_hints_and_the_command_to_turn_it_on(self):
        history(self.cfg, [("now", "p", VAGUE)])
        card = card_of(once(self.cfg, 100, 40))
        self.assertIn("Improve", card); self.assertIn("carefully/best/clean", card)
        self.assertIn("Press e for Claude's analysis", card)
        self.assertIn("setup.py --panel-ai on", card)


class Patterns(Base):
    def setUp(self):
        super().setUp()
        history(self.cfg, [("old1", "p", "write a commit message for the staged change please"), ("old2", "p", "give me a commit message for this diff"),
                           ("old3", "p", "need a commit message again for the next change"), ("now", "p", "one more commit message for the checkout change please")])
        self.write_json("learned.json", {"generated": "2026-09-30", "prompts": 120, "history_prompts": 120,
                                         "requests": [{"name": "commit-message", "keywords": ["commit message"], "count": 4}],
                                         "mistakes": [{"name": "no-reason-correction", "keywords": ["still broken"], "fix": "Say which rule it broke. Then add a test."}]})

    def test_patterns_are_one_collapsed_line_until_you_ask(self):
        out = once(self.cfg, 90, 40)
        self.assertIn("1 pattern from your past chats \u00b7 i to read", out)
        self.assertNotIn("You have asked for", out)                                   # not a wall of text over your prompts

    def test_i_expands_and_hides_them_in_plain_english(self):
        f = self.drive(["i", "i"])
        self.assertNotIn("You have asked for", f[0])
        text = flat(f[1])
        self.assertIn('You have asked for "commit-message" 4 times (3 before this thread): /coach review can draft a skill for it', text)
        self.assertIn("(120 prompts, 2026-09-30)", text)
        self.assertNotIn("0x", text); self.assertNotIn("Recurring gap", text)         # the jargon and the odd counts are gone
        self.assertNotIn("You have asked for", f[2])

    def test_a_drafted_skill_is_offered_and_s_installs_it_once(self):
        d = os.path.join(self.state_dir(), "drafts", "commit-message"); os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w") as f: f.write("---\nname: commit-message\ndescription: x\n---\nsteps\n")
        self.assertIn("1 pattern from your past chats \u00b7 i to read \u00b7 s installs a skill", once(self.cfg, 90, 40))

        class IO:
            def install(self, slug):
                import review
                return review.install_skill(slug)
        f = self.drive(["s", "i"], io=IO())
        self.assertIn("installed", f[1])
        self.assertTrue(os.path.isfile(os.path.join(self.cfg, "skills", "commit-message", "SKILL.md")))
        self.assertIn("youalreadyhave/commit-message,useit", flat(f[2]).replace(" ", ""))          # and no second offer

    def test_s_without_a_draft_says_so(self):
        self.assertIn("no drafted skill to install yet", self.drive(["s"])[1])

    def test_a_recurring_mistake_shows_only_when_this_thread_repeats_it(self):
        self.assertNotIn("Habit", flat(self.drive(["i"])[1]))
        history(self.cfg, [("old1", "p", "still broken after the first try please fix it again"), ("old2", "p", "it is still broken after the second try as well"),
                           ("now", "p", "now it is still broken after the third try and I am stuck")])
        text = flat(self.drive(["i"])[1])
        self.assertIn("Habit: no reason correction, seen 3 times. Say which rule it broke.", text)   # only the first sentence of the fix

    def test_nothing_is_shown_when_no_pattern_matches_this_thread(self):
        history(self.cfg, [("old1", "p", "write a commit message for this"), ("now", "p", "explain how the invoice cache works in detail")])
        out = once(self.cfg, 90, 40)
        self.assertNotIn("from your past chats", out)

    def test_it_says_what_claude_is_doing_while_there_is_nothing_to_show_yet(self):
        os.remove(os.path.join(self.state_dir(), "learned.json"))
        self.assertNotIn("analyse your past chats", once(self.cfg))                       # analysis off: silence
        self.write_json("config.json", {"panel_ai": True})
        self.assertIn("Claude will analyse your past chats in the background", once(self.cfg))
        with open(os.path.join(self.state_dir(), "review.running"), "w") as f: f.write("x")
        self.assertIn("Claude is analysing your past chats now", once(self.cfg))


class Analysis(Base):
    def test_the_card_shows_improvements_the_enhanced_prompt_and_web_finds(self):
        history(self.cfg, [("now", "p", SOLID)])                                          # passed every rule: still analysed
        self.analyse(0, SOLID, discovery=[{"name": "GreatKit", "kind": "tool", "why": "better", "url": "https://x.example.com/g", "install": "npm i g",
                                           "stars": 1200, "pushed": "2026-08-01"}])
        card = card_of(once(self.cfg, 100, 50))
        for want in ("refactoring \u00b7 tax rework", "Improve", "\u2022 Ask for every usage first.", "\u2022 use /simplify: clean up after", "\u2022 get shiny@mk: codemods",
                     "Enhanced prompt \u00b7 c to copy", "Rework the tax code in the invoice module.", "Done when: the unit tests pass.",
                     "Worth a look (found on the web, not installed)", "better: GreatKit (tool)", "install: npm i g"):
            self.assertIn(want, card)

    def test_the_full_view_adds_the_task_and_the_workflow(self):
        history(self.cfg, [("now", "p", SOLID)]); self.analyse(0, SOLID)
        d = flat(self.drive(["enter"], W=100, H=40)[1])
        for want in ("YOUR PROMPT", "CAN BE IMPROVED", "task: refactoring", "flow: 1) Search 2) Rename 3) Test", "ENHANCED PROMPT", "press c to copy"):
            self.assertIn(want, d)


class Navigation(Base):
    def setUp(self):
        super().setUp()
        history(self.cfg, [("now", "p", f"P{i:02d} " + VAGUE) for i in range(1, 13)])

    def test_up_and_down_choose_the_prompt_shown_in_the_card(self):
        f = self.drive(["up", "up", "down"])
        self.assertIn("P12", card_of(f[0]))
        self.assertIn("P11", card_of(f[1])); self.assertIn("P10", card_of(f[2])); self.assertIn("P11", card_of(f[3]))
        self.assertIn("an earlier prompt: G = newest", card_of(f[1]))

    def test_home_and_end_jump_to_the_oldest_and_the_newest(self):
        f = self.drive(["home", "end"])
        self.assertIn("P01", card_of(f[1])); self.assertIn("P12", card_of(f[2]))
        self.assertNotIn("an earlier prompt", card_of(f[2]))

    def test_the_list_scrolls_to_keep_the_selected_row_visible(self):
        f = self.drive(["home"], W=90, H=24)
        self.assertTrue(any("P01" in r and "\u203a" in r for r in list_of(f[1])))

    def test_a_new_prompt_takes_over_the_card_only_while_you_are_on_the_newest(self):
        def run(seq):
            t, it, frames = [0], iter(seq), []
            def clock(): t[0] += 3; return t[0]
            def load():
                if t[0] > 3: history(self.cfg, [("now", "p", f"P{i:02d} " + VAGUE) for i in range(1, 14)])      # P13 arrives after the first load
                return watch.build(self.path)
            watch.loop(lambda _t: next(it, "q"), lambda rows: frames.append("\n".join(rows)), lambda: (100, 30), load, clock=clock)
            return card_of(frames[-1])
        self.assertIn("P13", run([None, None]))                                          # on the newest: follows the new prompt
        history(self.cfg, [("now", "p", f"P{i:02d} " + VAGUE) for i in range(1, 13)])
        self.assertIn("P11", run(["up", None, None]))                                    # chosen an earlier one: it stays put

    def test_pgdn_scrolls_a_card_taller_than_the_pane(self):
        self.analyse(11, "P12 " + VAGUE)
        f = self.drive(["pgdn", "pgup"], W=60, H=13)
        self.assertIn("PgDn for more", f[0])
        self.assertNotEqual(card_of(f[0]), card_of(f[1]))
        self.assertIn("PgUp for the start", f[1])
        self.assertEqual(card_of(f[0]), card_of(f[2]))

    def test_the_footer_always_fits_and_keeps_the_most_important_keys_first(self):
        for W in (30, 36, 44, 56, 70, 100):
            line = plain(watch.render(watch.build(self.path), watch.new_ui(), W, 24, color=False)[-1])
            self.assertLessEqual(len(line), W - 1, W)
            self.assertIn("\u2191\u2193 prompt", line)                                   # the first key is never the one that gets cut
        self.assertIn("q quit", plain(watch.render(watch.build(self.path), watch.new_ui(), 100, 24, color=False)[-1]))

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
            if calls[0] > 1: history(self.cfg, [("now", "p", f"P{i:02d} " + VAGUE) for i in range(1, 14)])
            return watch.build(self.path)

        watch.loop(keys, lambda rows: writes.append(rows), lambda: (100, 30), load, clock=clock)
        self.assertEqual(len(writes), 2)                                # new data means exactly one more draw

    def test_the_key_tables(self):
        self.assertEqual(watch.POSIX_KEYS["[A"], "up"); self.assertEqual(watch.WIN_KEYS["P"], "down")
        a = watch.ALIASES
        self.assertEqual((a["\r"], a["\x1b"], a["c"], a["e"], a["s"], a["i"], a["j"], a["k"], a["n"], a["p"]),
                         ("enter", "esc", "copy", "enhance", "skill", "patterns", "down", "up", "down", "up"))
        ui, st = watch.new_ui(), watch.build(self.path)
        self.assertFalse(watch.handle(ui, st, "j")); self.assertTrue(watch.handle(ui, st, "q")); self.assertTrue(watch.handle(ui, st, "\x03"))

    @unittest.skipIf(os.name == "nt", "needs a POSIX pty; the Windows msvcrt path is not covered by tests")
    def test_real_keyboard_in_a_pty(self):
        import pty, select
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
            os.write(fd, b"\x1b[A")                            # the up-arrow key, as a terminal sends it
            self.assertTrue(read_until("an earlier prompt"), buf[-300:])
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
