import json, os, re, subprocess, sys, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach, memory, watch  # noqa: E402
os.environ["COACHLINE_PLATFORM"] = "Windows"   # these tests pin the opt-in defaults; tests/test_defaults.py covers macOS and Linux

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
    lines = plain(frame).replace("\u2503", " ").splitlines()                 # the coloured gutter bars are decoration
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
        self.write_json("config.json", {"panel_ai": False})        # analysis is on by default everywhere; these tests start with it off

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
            self.assertIn("Enhanced prompt", card, (W, H)); self.assertIn("c Copy", card, (W, H))
            self.assertIn("Done when: the unit tests pass.", card, (W, H))           # the whole thing, not just its first line

    def test_improve_is_never_cut_and_what_does_not_fit_scrolls(self):
        long_tip = "Describe the current layout and the target one, then name the width where the lines wrap and overlap so nothing is guessed " * 2
        tips = [long_tip.strip(), "Name the files that must not change.", "Say what done looks like."]
        self.analyse(11, "P12 " + VAGUE, advice={**ADVICE, "tips": tips})
        want = {w for t in tips + ["use /simplify: clean up after", "get shiny@mk: codemods"] for w in t.split()}
        for W, H in [(44, 22), (56, 34), (70, 21), (90, 40), (120, 50)]:
            seen, ellipsis = set(), False
            for frame in self.drive(["pgdn"] * 8, W=W, H=H):                                     # look at every scroll position
                card = card_of(frame)
                improve = (card.split("Improve", 1)[1] if "Improve" in card else card).split("Enhanced prompt")[0]     # the header itself may have scrolled off
                seen |= set(improve.replace("PgUp for the start", " ").replace("PgDn for more", " ").split())
                ellipsis = ellipsis or "…" in improve
            self.assertFalse(want - seen, (W, H, want - seen))                                   # every word of every tip was shown
            self.assertFalse(ellipsis, (W, H))                                                   # and nothing was ever cut with an ellipsis
        for W, H in [(90, 40), (120, 50)]:                                                       # where it fits, nothing needs scrolling
            self.assertFalse(want - set(card_of(once(self.cfg, W, H)).split()), (W, H))
        self.assertIn("PgDn for more", once(self.cfg, 44, 22))                                   # a tall card says so at the bottom
        self.assertIn("Enhanced prompt", card_of(self.drive(["pgdn"] * 4, W=44, H=22)[-1]))      # and PgDn reaches the enhanced prompt

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
        self.assertIn("\x1b[1;97mUNIQUEPROMPT", prompt)                                   # bright white, after a white gutter bar
        self.assertIn("\x1b[97m\u2503", prompt)
        label = next(r for r in rows if "Improve" in r)
        self.assertIn("\x1b[1;94mImprove", label)                                         # bright blue title and gutter
        hint = next(r for r in rows if "carefully/best/clean" in r)
        self.assertIn("\x1b[94m\u2022", hint)

    def test_claudes_advice_and_the_enhanced_prompt_are_blue_too(self):
        self.analyse(0, "UNIQUEPROMPT " + VAGUE)
        rows = self.rows()
        for needle in ("Ask for every usage first.", "Rework the tax code"):
            row = next(r for r in rows if needle in r)
            self.assertIn("\x1b[94m", row.split(needle)[0].split("┃")[-1])             # the text after the gutter bar is blue

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
        for want in ("Improve refactoring", "tax rework", "\u2022 Ask for every usage first.", "\u2022 use /simplify: clean up after", "\u2022 get shiny@mk: codemods",
                     "Enhanced prompt c Copy", "Rework the tax code in the invoice module.", "Done when: the unit tests pass.",
                     "Worth a look found on the web, not installed", "better: GreatKit (tool)", "install: npm i g"):
            self.assertIn(want, card)

    def test_the_full_view_adds_the_task_and_the_workflow(self):
        history(self.cfg, [("now", "p", SOLID)]); self.analyse(0, SOLID)
        d = flat(self.drive(["enter"], W=100, H=40)[1])
        for want in ("YOUR PROMPT", "CAN BE IMPROVED", "task: refactoring", "flow: 1) Search 2) Rename 3) Test", "ENHANCED PROMPT", "press c to copy"):
            self.assertIn(want, d)


class WideText(Base):
    """CJK and emoji take two terminal columns; counting them as one makes lines wrap and the screen glitch."""
    def test_display_width_and_clipping_count_wide_characters_as_two(self):
        self.assertEqual((watch.dw("abc"), watch.dw("日本"), watch.dw("\U0001F680 go"), watch.dw("é")), (3, 4, 5, 1))
        self.assertEqual(watch.dw(watch.clip("日本語のテスト", 7)), 7)           # 3 wide characters plus the ellipsis
        self.assertTrue(all(watch.dw(l) <= 10 for l in watch.wrap("日本語 " * 12 + "x" * 30, 10)))
        self.assertEqual(watch.tidy("a\tb\x07c"), "a b c")                                          # no control characters reach the screen

    def test_a_prompt_full_of_wide_characters_never_overflows_the_pane(self):
        text = "これを直してください \U0001F680 " * 14 + "please make the invoice page faster for everyone"
        history(self.cfg, [("now", "p", text), ("now", "p", text + " again")])
        for W, H in [(40, 20), (56, 34), (90, 30)]:
            lines = watch.render(watch.build(self.path), watch.new_ui(), W, H, color=False)
            self.assertTrue(all(watch.dw(l) <= W - 1 for l in lines), (W, H, [watch.dw(l) for l in lines]))


class Mouse(Base):
    def setUp(self):
        super().setUp()
        history(self.cfg, [("now", "p", f"P{i:02d} " + VAGUE) for i in range(1, 13)])
        self.analyse(11, "P12 " + VAGUE)

    def frame(self, ui, st, W=90, H=40):
        return watch.render(st, ui, W, H, color=False)

    def test_the_input_parser_reads_keys_and_sgr_mouse_events(self):
        self.assertEqual(watch.parse_input("\x1b[A\x1b[B\x1b[5~q"), ["up", "down", "pgup", "q"])
        self.assertEqual(watch.parse_input("\x1bOA\x1b[H"), ["up", "home"])
        self.assertEqual(watch.parse_input("\x1b[<0;12;7M\x1b[<0;12;7m\x1b[<64;3;4M"), [("mouse", 0, 12, 7, True), ("mouse", 0, 12, 7, False), ("mouse", 64, 3, 4, True)])
        self.assertEqual(watch.parse_input("\x1b"), ["\x1b"])                            # a lone Escape (ALIASES turns it into 'esc')
        self.assertEqual(watch.parse_input("\x1b[<0;1"), [])                             # an unfinished sequence is dropped, not misread
        self.assertEqual(watch.parse_input("\x1b[1;5A\x1b[?1;2cx"), ["x"])              # modified arrows and terminal replies are ignored

    def test_input_that_arrives_in_pieces_is_put_back_together(self):
        p = watch.InputParser()
        got = []
        for piece in ("\x1b", "[", "<", "0;", "2", "0", ";1", "3M", "\x1b[<64;", "20;13", "M", "q"):               # how Windows delivered one click
            got += p.feed(piece)
        self.assertEqual(got, [("mouse", 0, 20, 13, True), ("mouse", 64, 20, 13, True), "q"])
        self.assertEqual(p.feed("\x1b"), []); self.assertEqual(p.flush(), ["\x1b"])                      # a lone ESC waits, then is Escape
        self.assertEqual(p.feed("\x1b[A"), ["up"])                                                        # ...but not when an arrow follows it
        self.assertEqual(p.feed("\x1b[<0;1"), []); self.assertEqual(p.flush(), [])                        # an unfinished report is dropped

    def test_only_the_press_of_a_wheel_notch_scrolls(self):
        st = watch.build(self.path); ui = watch.new_ui(); self.frame(ui, st, 60, 16)
        r = ui["list_rows"][0] + 1
        watch.handle(ui, st, ("mouse", 64, 10, r, True)); watch.handle(ui, st, ("mouse", 64, 10, r, False))
        self.assertEqual(ui["sel"], 10)                                                  # one notch, one step

    def test_a_click_on_a_list_row_selects_that_prompt(self):
        st = watch.build(self.path); ui = watch.new_ui(); f = self.frame(ui, st)
        row = next(n for n, l in enumerate(f) if "P09" in l and "›" not in l)
        self.assertFalse(watch.handle(ui, st, ("mouse", 0, 21, row + 1, True)))
        self.assertIn("P09", card_of("\n".join(self.frame(ui, st))))
        f = self.frame(ui, st)
        newest = next(n for n, l in enumerate(f) if "P12" in l and l.startswith("   "))
        watch.handle(ui, st, ("mouse", 0, 21, newest + 1, True))
        self.assertIsNone(ui["sel"])                                                     # back on the newest: it follows new prompts again

    def test_the_copy_button_and_the_footer_buttons_are_clickable(self):
        class IO:
            copied = []
            def copy(self, t): self.copied.append(t); return "test clipboard"
        io = IO(); st = watch.build(self.path); ui = watch.new_ui(); f = self.frame(ui, st)
        row = next(n for n, l in enumerate(f) if "Enhanced prompt" in l); col = f[row].index("c Copy") + 1
        watch.handle(ui, st, ("mouse", 0, col + 1, row + 1, True), io)
        self.assertEqual(io.copied, [ADVICE["after"]])
        self.assertIn("copied the enhanced prompt", ui["msg"])
        ui = watch.new_ui(); f = self.frame(ui, st)
        foot = len(f) - 1; col = f[foot].index("i patterns")
        watch.handle(ui, st, ("mouse", 0, col + 1, foot + 1, True), io)
        self.assertTrue(ui["patterns"])                                                  # the footer button did what the key does
        watch.handle(ui, st, ("mouse", 0, 1, foot + 1, True), io)                        # a click on empty space does nothing
        watch.handle(ui, st, ("mouse", 2, col + 1, foot + 1, True), io)                  # nor does a right click
        self.assertTrue(ui["patterns"])

    def test_the_wheel_moves_the_selection_over_the_list_and_scrolls_the_card_elsewhere(self):
        st = watch.build(self.path); ui = watch.new_ui(); self.frame(ui, st, 60, 16)
        lr = ui["list_rows"]
        watch.handle(ui, st, ("mouse", 64, 10, lr[0] + 1, True))                         # wheel up over the list
        self.assertEqual(ui["sel"], 10)
        watch.handle(ui, st, ("mouse", 65, 10, lr[0] + 1, True))
        self.assertIsNone(ui["sel"])
        watch.handle(ui, st, ("mouse", 65, 10, 4, True))                                 # wheel down over the card
        self.assertGreater(ui["cs"], 0)
        watch.handle(ui, st, ("mouse", 64, 10, 4, True))
        self.assertEqual(ui["cs"], 0)

    def test_m_switches_mouse_reporting_so_you_can_select_text(self):
        emitted, it, frames = [], iter(["m", "m"]), []
        watch.loop(lambda t: next(it, "q"), lambda rows: frames.append("\n".join(rows)), lambda: (100, 30), lambda: watch.build(self.path), emit=emitted.append)
        self.assertEqual(emitted, [watch.MOUSE_OFF, watch.MOUSE_ON])
        self.assertIn("mouse off: select and copy text", frames[1]); self.assertIn("mouse on: wheel scrolls", frames[2])


class PaneSize(unittest.TestCase):
    """A pane inherits COLUMNS / LINES from whatever opened it (Claude Code's hook), so they describe some other window. Drawing for that
    width and letting the real, narrower pane cut the lines mid-word was the 'panel is broken' report."""

    def test_the_size_comes_from_the_terminal_not_from_the_environment(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {"COLUMNS": "100", "LINES": "30"}), \
                mock.patch.object(watch.os, "get_terminal_size", lambda fd: os.terminal_size((51, 28))):
            self.assertEqual(watch.term_size(), (51, 28))

    def test_when_nothing_can_be_asked_it_is_a_standard_small_terminal_not_the_environment(self):
        from unittest import mock

        def boom(*a): raise OSError("not a terminal")
        with mock.patch.dict(os.environ, {"COLUMNS": "200", "LINES": "70"}), mock.patch.object(watch.os, "get_terminal_size", boom), \
                mock.patch.object(watch.os, "open", boom), mock.patch.object(watch.os, "name", "posix"):
            self.assertEqual(watch.term_size(), (80, 24))

    def test_a_real_pty_of_51_columns_is_drawn_for_51_even_with_columns_set_to_100(self):
        if os.name == "nt": self.skipTest("needs a POSIX pty; the Windows path was checked in a real Windows Terminal split")
        import fcntl, pty, select, struct, termios
        with tempfile.TemporaryDirectory() as cfg:
            history(cfg, [("now", "p", "Create a modern luxury premium website for shoe selling with astro frontend " * 2)])
            pid, fd = pty.fork()
            if pid == 0:
                os.environ.update({"CLAUDE_CONFIG_DIR": cfg, "TERM": "xterm", "COLUMNS": "100", "LINES": "30", "PYTHONIOENCODING": "utf-8"})
                os.execv(sys.executable, [sys.executable, os.path.join(ROOT, "scripts", "watch.py")])
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 51, 0, 0))      # the pane is 51 columns wide
            buf, end = "", time.time() + 10
            try:
                while "Prompts in this thread" not in buf and time.time() < end:
                    if select.select([fd], [], [], 0.2)[0]:
                        try: buf += os.read(fd, 65536).decode("utf-8", "ignore")
                        except OSError: break
                os.write(fd, b"q")
            finally:
                try: os.kill(pid, 9)
                except OSError: pass
            frame = buf.split("\x1b[H")[1] if "\x1b[H" in buf else buf                  # the first full frame
            lines = [re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", l) for l in frame.split("\x1b[K\r\n")]      # the pty turns \n into \r\n
            self.assertTrue(lines and all(watch.dw(l) <= 50 for l in lines), [watch.dw(l) for l in lines])      # nothing is wider than the pane


class Resume(Base):
    """Resuming logs '/resume' under a throwaway session id and nothing for the resumed session until you send a prompt; the panel
    showed '0 prompts in this thread'. The conversation you are in is the one whose transcript Claude Code wrote last."""

    def transcript(self, sid, age):
        d = os.path.join(self.cfg, "projects", "C--proj"); os.makedirs(d, exist_ok=True)
        p = os.path.join(d, sid + ".jsonl")
        with open(p, "w") as f: f.write("{}\n")
        t = time.time() - age; os.utime(p, (t, t))

    def setUp(self):
        super().setUp()
        history(self.cfg, [("shoes", "p", "SHOES one create a luxury shoe website with astro"), ("shoes", "p", "SHOES two add a product catalog page please"),
                           ("audit", "p", "AUDIT one audit how i use claude code in detail"), ("audit", "p", "AUDIT two fix what is fixable from the report"),
                           ("throwaway", "p", "/resume")])

    def entries(self):
        return [e["text"] for e in watch.build(self.path)["entries"]]

    def test_the_resumed_session_is_shown_not_the_empty_throwaway_one(self):
        self.transcript("audit", 600); self.transcript("shoes", 5)                # you just resumed the shoe session: its transcript was touched
        self.assertEqual(self.entries(), ["SHOES one create a luxury shoe website with astro", "SHOES two add a product catalog page please"])
        self.transcript("audit", 1); self.transcript("shoes", 300)                # then you resume the audit session
        self.assertEqual([t[:9] for t in self.entries()], ["AUDIT one", "AUDIT two"])

    def test_a_fresh_session_announced_by_the_hook_is_empty_not_the_previous_conversation(self):
        self.transcript("shoes", 100)                                             # an older conversation, last written 100 s ago
        coach.record_session(json.dumps({"session_id": "fresh-session-1234", "source": "startup"}))
        st = watch.build(self.path)
        self.assertEqual((st["session"], st["entries"]), ("fresh-session-1234", []))
        self.assertIn("No prompts in this thread yet.", "\n".join(watch.render(st, watch.new_ui(), 80, 20, color=False)))
        self.transcript("shoes", -5)                                              # then you resume the shoe session: its transcript is written later
        self.assertEqual(watch.build(self.path)["session"], "shoes")
        coach.record_session(json.dumps({"session_id": "fresh-session-1234", "source": "clear"}))   # /clear starts another empty one
        self.transcript("shoes", 300)
        self.assertEqual(watch.build(self.path)["session"], "fresh-session-1234")

    def test_the_hook_record_ignores_resume_events_and_bad_input(self):
        for payload in ("not json", "[]", json.dumps({"session_id": "../../evil", "source": "startup"}), json.dumps({"session_id": "short", "source": "startup"}),
                        json.dumps({"session_id": "abcd1234-aaaa-bbbb", "source": "resume"}), json.dumps({"session_id": "abcd1234-aaaa-bbbb"})):
            coach.record_session(payload)
            self.assertIsNone(coach.started_session(), payload)                    # a resumed session is found by its transcript instead
        coach.record_session(json.dumps({"session_id": "abcd1234-aaaa-bbbb", "source": "startup"}))
        self.assertEqual(coach.started_session()[0], "abcd1234-aaaa-bbbb")

    def test_a_session_with_no_transcript_is_never_chosen_over_one_with_a_transcript(self):
        self.transcript("audit", 100)                                             # 'throwaway' has no file, as in real life
        self.assertEqual(watch.build(self.path)["session"], "audit")

    def test_without_any_transcripts_it_is_the_newest_prompt_that_is_not_a_command(self):
        self.assertEqual(watch.build(self.path)["session"], "audit")              # '/resume' is skipped
        history(self.cfg, [("shoes", "p", "/clear")])
        self.assertEqual(watch.build(self.path)["session"], "shoes")              # only commands: the last session seen

    def test_the_panel_switches_to_the_other_conversation_and_starts_at_its_newest_prompt(self):
        self.transcript("audit", 10); self.transcript("shoes", 500)
        t, it, frames = [0], iter(["up", None, None]), []
        state = {"n": 0}

        def clock(): t[0] += 3; return t[0]

        def load():
            state["n"] += 1
            if state["n"] > 1: self.transcript("shoes", 0)                         # resume: the shoe transcript becomes the newest
            return watch.build(self.path)
        watch.loop(lambda _t: next(it, "q"), lambda rows: frames.append("\n".join(rows)), lambda: (100, 30), load, clock=clock)
        self.assertIn("AUDIT one", card_of(frames[1]))                             # you had moved up to the earlier audit prompt
        self.assertIn("SHOES two", card_of(frames[-1]))                            # then the thread changed: the newest prompt of the new one
        self.assertNotIn("earlier prompt", card_of(frames[-1]))


class Navigation(Base):
    def setUp(self):
        super().setUp()
        history(self.cfg, [("now", "p", f"P{i:02d} " + VAGUE) for i in range(1, 13)])

    def test_up_and_down_choose_the_prompt_shown_in_the_card(self):
        f = self.drive(["up", "up", "down"])
        self.assertIn("P12", card_of(f[0]))
        self.assertIn("P11", card_of(f[1])); self.assertIn("P10", card_of(f[2])); self.assertIn("P11", card_of(f[3]))
        self.assertIn("earlier prompt, G = newest", card_of(f[1]))

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
            self.assertIn("\033[?1000h\033[?1006h", buf)       # mouse reporting is on
            self.assertTrue(read_until("earlier prompt, G = newest"), buf[-300:])
            os.write(fd, b"c")                                 # copy with no enhanced prompt yet: a message, proving the key was read
            self.assertTrue(read_until("no enhanced prompt yet"), buf[-300:])
            os.write(fd, b"m")                                 # mouse off, so the terminal's own text selection works again
            self.assertTrue(read_until("mouse off: select and copy text"), buf[-300:])
            self.assertIn("\033[?1000l", buf)
            os.write(fd, b"m"); self.assertTrue(read_until("mouse on: wheel scrolls"), buf[-300:])
            os.write(fd, b"\x1b[<65;5;5M")                     # a wheel notch over the card (SGR mouse report, as the terminal sends it)
            os.write(fd, b"j")                                 # down to the newest prompt; the footer is back
            # click the footer's "q quit" button at the place the layout says it is
            ui = watch.new_ui(); watch.render(watch.build(self.path), ui, 100, 30, color=False)
            row, c0, c1, _a = next(h for h in ui["hits"] if h[3] == "q")
            os.write(fd, f"\x1b[<0;{c0 + 2};{row + 1}M".encode())
            self.assertTrue(read_until("\033[?1049l"), buf[-200:])   # terminal restored on quit, by a click
            _, status = os.waitpid(pid, 0)
            self.assertEqual(os.WEXITSTATUS(status), 0)
        finally:
            try: os.kill(pid, 9)
            except OSError: pass


class ForcedSession(unittest.TestCase):
    def test_build_shows_only_the_session_it_is_given(self):
        with tempfile.TemporaryDirectory() as cfg:
            history(cfg, [("s1", "p", VAGUE), ("s2", "p", SOLID)])
            st = watch.build(os.path.join(cfg, "history.jsonl"), session="s1")
            self.assertEqual(st["session"], "s1")
            self.assertEqual([e["text"] for e in st["entries"]], [VAGUE])

    def test_a_session_with_no_prompts_yet_has_no_entries(self):
        with tempfile.TemporaryDirectory() as cfg:
            history(cfg, [("s1", "p", VAGUE)])
            st = watch.build(os.path.join(cfg, "history.jsonl"), session="brand-new")
            self.assertEqual(st["entries"], [])



class Notice(unittest.TestCase):
    def test_the_standalone_panel_shows_the_notice_too(self):
        with tempfile.TemporaryDirectory() as cfg:
            history(cfg, [("s1", "p", VAGUE)])
            env = {**os.environ, "COACHLINE_PLATFORM": "Darwin", "CLAUDE_CONFIG_DIR": cfg, "PYTHONIOENCODING": "utf-8"}
            r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "watch.py"), "--once", "--width", "100", "--height", "40"],
                               capture_output=True, text=True, encoding="utf-8", env=env, input="")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("prompts go redacted to your subscription", flat(r.stdout))


WCAG = {"name": "WCAG 2.2", "kind": "docs", "why": "accessibility rules to follow", "url": "https://www.w3.org/TR/WCAG22/", "install": "", "stars": None, "pushed": None}
KIT = {"name": "GreatKit", "kind": "tool", "why": "better", "url": "https://x.example.com/g", "install": "npm i g", "stars": None, "pushed": None}


class Research(Base):
    def setUp(self):
        super().setUp(); history(self.cfg, [("now", "p", SOLID)])

    def entry(self):
        return watch.build(self.path)["entries"][0]

    def test_research_adds_references_to_the_enhanced_prompt_you_copy(self):
        self.analyse(0, SOLID, discovery=[WCAG, KIT])
        e = self.entry()
        self.assertTrue(e["after"].endswith("References (checked links from web research):\n"
                                            "- Follow WCAG 2.2: https://www.w3.org/TR/WCAG22/\n- Use GreatKit: https://x.example.com/g"))
        card = card_of(once(self.cfg, 100, 60))
        for want in ("1. better: WCAG 2.2 (docs)", "2. better: GreatKit (tool)", "Includes references from web research: x hides one"):
            self.assertIn(want, card)

    def test_a_hidden_suggestion_leaves_the_card_and_the_references_and_a_used_one_is_marked(self):
        self.analyse(0, SOLID, discovery=[WCAG, KIT])
        memory.mark(memory.item_id(KIT), "dismissed"); memory.mark(memory.item_id(WCAG), "adopted")
        e = self.entry()
        self.assertEqual([x["name"] for x in e["items"]], ["WCAG 2.2"]); self.assertNotIn("GreatKit", e["after"])
        self.assertIn("1. better: WCAG 2.2 (docs) · you use this", " ".join(t for _k, t in e["disc"]))

    def test_no_references_without_an_enhanced_prompt_or_without_research(self):
        self.analyse(0, SOLID)
        self.assertNotIn("References", self.entry()["after"]); self.assertFalse(self.entry()["refs"])

    def test_p1_records_still_show_with_references(self):
        self.analyse(0, SOLID, discovery=[{"name": "OldKit", "kind": "mcp", "why": "old", "url": "https://old.example.com/k", "install": "", "stars": 5, "pushed": None}])
        e = self.entry()
        self.assertIn("- Use OldKit: https://old.example.com/k", e["after"])
        self.assertIn("1. better: OldKit (mcp)", " ".join(t for _k, t in e["disc"]))

    def test_research_landing_redraws_the_standalone_panel(self):
        self.analyse(0, SOLID)
        before = watch.signature(watch.build(self.path))
        self.analyse(0, SOLID, discovery=[KIT])
        self.assertNotEqual(before, watch.signature(watch.build(self.path)))

    def test_the_pane_gets_hide_and_use_actions_per_item(self):
        self.analyse(0, SOLID, discovery=[WCAG, KIT])
        st = watch.build(self.path); e = st["entries"][0]
        acts = [l[4] for l in watch.card_lines(st, watch.new_ui(), 0, e, 80, acts=True) if l[1] == "itemacts"]
        self.assertEqual(acts, ["item:w3.org/tr/wcag22", "item:x.example.com/g"])
        self.assertFalse([l for l in watch.card_lines(st, watch.new_ui(), 0, e, 80) if l[1] == "itemacts"])   # never in the terminal panel


class WebIO:
    def __init__(self): self.marks, self.researched, self.copied = [], [], []
    def mark(self, iid, status): self.marks.append((iid, status)); return memory.mark(iid, status)
    def research(self, key): self.researched.append(key)
    def copy(self, text): self.copied.append(text); return "fake"


class WebKeys(Base):
    def setUp(self):
        super().setUp(); history(self.cfg, [("now", "p", SOLID)]); self.io = WebIO()

    def test_x_then_a_number_hides_that_suggestion_and_the_copy_follows(self):
        self.analyse(0, SOLID, discovery=[WCAG, KIT])
        frames = self.drive(["x", "2", "c"], W=100, H=60, io=self.io)
        self.assertEqual(self.io.marks, [("x.example.com/g", "dismissed")])
        self.assertIn("press 1-2", frames[1])
        self.assertIn("hidden: GreatKit will not be suggested again", flat(frames[2])); self.assertNotIn("better: GreatKit", frames[2])
        self.assertNotIn("GreatKit", self.io.copied[0]); self.assertIn("WCAG 2.2", self.io.copied[0])

    def test_with_one_suggestion_a_marks_it_at_once(self):
        self.analyse(0, SOLID, discovery=[KIT])
        frames = self.drive(["a"], io=self.io)
        self.assertEqual(self.io.marks, [("x.example.com/g", "adopted")]); self.assertIn("noted: you use GreatKit", flat(frames[-1]))

    def test_any_other_key_cancels_the_choice(self):
        self.analyse(0, SOLID, discovery=[WCAG, KIT])
        self.drive(["x", "esc", "2", "a", "j", "1"], io=self.io)
        self.assertEqual(self.io.marks, [])

    def test_x_without_suggestions_says_so(self):
        self.analyse(0, SOLID)
        self.assertIn("no web suggestions on this prompt", flat(self.drive(["x"], io=self.io)[-1]))

    def test_r_researches_the_selected_prompt_again_once_it_is_analysed(self):
        self.assertIn("analyse this prompt first", flat(self.drive(["r"], io=self.io)[-1]))
        self.analyse(0, SOLID)
        frames = self.drive(["r"], io=self.io)
        self.assertEqual(self.io.researched, [key_for(0, SOLID)]); self.assertIn("searching the web", flat(frames[-1]))


if __name__ == "__main__":
    unittest.main()
