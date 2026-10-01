import json, os, re, subprocess, sys, tempfile, unittest

from test_review import run, read
from test_watch import Base, history, once, flat, T0, VAGUE
import coach, watch

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_claude.py").replace("\\", "/")
SINK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clip_sink.py").replace("\\", "/")
PY = sys.executable.replace("\\", "/")
AFTER = "Goal: make checkout faster [Pasted text #1 +28 lines].\nDone when: p95 under 300ms.\nAsk: [ASK: which page?] <email>"
ADVICE = {"task": "backend", "summary": "speeding up checkout", "use": [], "get": [], "tips": ["Give a number."], "workflow": ["Measure", "Fix"], "after": AFTER}


class Fake:
    """Stands in for watch.IO: records what the panel asked for."""
    def __init__(self, copy_ok="fake clipboard"):
        self.copied, self.enhanced, self.copy_ok = [], [], copy_ok

    def copy(self, text):
        self.copied.append(text)
        return self.copy_ok

    def enhance(self, key):
        self.enhanced.append(key)

    def review(self):
        self.reviews = getattr(self, "reviews", 0) + 1

    def install(self, slug):
        return True, "installed " + slug


def key_for(i, text, proj="p"):
    return coach.prompt_key((float(T0 + i * 90000) / 1000, proj, text))


class Panel(Base):
    def setUp(self):
        super().setUp()
        self.prompts = [VAGUE + f" P{i:02d}" for i in range(1, 4)]
        history(self.cfg, [("now", "p", t) for t in self.prompts])
        self.io = Fake()

    def frames(self, keys, W=100, H=30):
        out, it = [], iter(keys)
        watch.loop(lambda t: next(it, "q"), lambda rows: out.append("\n".join(rows)), lambda: (W, H), lambda: watch.build(self.path), io=self.io)
        return out

    def add_advice(self, i, advice=ADVICE):
        os.makedirs(os.path.join(self.cfg, "coach"), exist_ok=True)
        with open(os.path.join(self.cfg, "coach", "rewrites.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key_for(i, self.prompts[i]), "text": "AFTER: " + advice["after"], "advice": advice}) + "\n")

    def marked(self, frame):
        """The prompt text under the '* HH:MM' marker."""
        lines = re.sub(r"\x1b\[[0-9;]*m", "", frame).splitlines(); n = next(i for i, l in enumerate(lines) if re.search(r"\* \d\d:\d\d", l))
        return " ".join(lines[n + 1:n + 4])

    def test_the_newest_prompt_is_selected_and_n_p_move_the_marker(self):
        f = self.frames(["p", "p", "n"])
        self.assertIn("P03", self.marked(f[0]))
        self.assertIn("P02", self.marked(f[1]))
        self.assertIn("P01", self.marked(f[2]))
        self.assertIn("P02", self.marked(f[3]))

    def test_moving_the_selection_scrolls_it_into_view(self):
        history(self.cfg, [("now", "p", VAGUE + f" Q{i:02d}") for i in range(1, 13)])
        f = self.frames(["p"] * 11, W=100, H=14)
        self.assertNotIn("Q01", f[0])                         # oldest is off screen at first
        self.assertIn("Q01", f[-1])                           # ...and visible once selected
        self.assertIn("Q01", self.marked(f[-1]))

    def test_enter_opens_the_full_width_detail_view_and_esc_returns(self):
        self.add_advice(2)
        f = self.frames(["enter", "esc"], W=110, H=34)
        d = f[1]
        for want in ("YOUR PROMPT", "CAN BE IMPROVED", "task: backend", "ENHANCED PROMPT", "press c to copy"):
            self.assertIn(want, d)
        self.assertIn("Goal: make checkout faster [Pasted text #1 +28 lines].", d)   # the enhanced prompt, plain, marker kept
        self.assertNotIn("│", d)                                                     # no column separators to spoil a mouse selection
        self.assertNotIn("AFTER:", d)                                                # printed once, in its own block
        self.assertIn("this thread", f[2]); self.assertNotIn("YOUR PROMPT", f[2])

    def test_detail_view_says_what_to_do_when_there_is_no_enhanced_prompt(self):
        f = self.frames(["enter"])
        self.assertIn("none yet. Press e", f[1])

    def test_c_copies_the_enhanced_prompt_exactly_as_written(self):
        self.add_advice(2)
        f = self.frames(["c"])
        self.assertEqual(self.io.copied, [AFTER])             # multi-line, placeholders and marker untouched, no wrapping
        self.assertIn(f"copied the enhanced prompt ({len(AFTER)} characters) via fake clipboard", f[1])

    def test_c_without_an_enhanced_prompt_copies_nothing_and_says_why(self):
        f = self.frames(["c"])
        self.assertEqual(self.io.copied, [])
        self.assertIn("press e", f[1])

    def test_c_reports_a_missing_clipboard(self):
        self.add_advice(2); self.io.copy_ok = None
        self.assertIn("no clipboard available here", self.frames(["c"])[1])

    def test_e_asks_claude_once_for_the_selected_prompt_only(self):
        f = self.frames(["p", "e", "e"])                     # select P02, ask twice
        self.assertEqual(self.io.enhanced, [key_for(1, self.prompts[1])])
        self.assertIn("asking Claude in the background", f[2])
        self.assertIn("already asking Claude", f[3])
        self.assertIn("Claude is analysing this prompt... (about 20s)", f[2])

    def test_e_refuses_projects_in_the_opt_out_list_and_already_enhanced_prompts(self):
        os.makedirs(os.path.join(self.cfg, "coach"))
        with open(os.path.join(self.cfg, "coach", "llm-off.txt"), "w") as f: f.write("secret-proj\n")
        history(self.cfg, [("now", "D:/w/secret-proj", VAGUE + " S01")])
        f = self.frames(["e"])
        self.assertEqual(self.io.enhanced, [])
        self.assertIn("llm-off.txt", f[1])
        history(self.cfg, [("now", "p", t) for t in self.prompts]); self.add_advice(2)
        f = self.frames(["e"])
        self.assertEqual(self.io.enhanced, [])
        self.assertIn("already analysed", f[1])

    def test_windows_raw_keys_map_to_actions(self):
        self.assertEqual((watch.ALIASES["\r"], watch.ALIASES["\x1b"], watch.ALIASES["c"], watch.ALIASES["e"]), ("enter", "esc", "copy", "enhance"))


class EnhanceOneJob(Base):
    """`coach.py --bg-rewrite --key K` is what the panel's `e` starts."""
    ADV = json.dumps(ADVICE)

    def setUp(self):
        super().setUp()
        self.text = VAGUE + " Z01"
        history(self.cfg, [("now", "p", "warm up the earlier thing first please now"), ("now", "p", self.text), ("now", "p", VAGUE + " Z02")])
        self.key = key_for(1, self.text)

    def job(self, key, **env):
        return run(self.cfg, "coach.py", "--bg-rewrite", "--key", key, **env)

    def test_it_enhances_that_prompt_even_though_it_is_not_the_last_one(self):
        self.assertEqual(self.job(self.key, FAKE_JSON=self.ADV).returncode, 0)
        with open(os.path.join(self.cfg, "coach", "rewrites.jsonl"), encoding="utf-8") as f: recs = [json.loads(l) for l in f]
        self.assertEqual([r["key"] for r in recs], [self.key])
        self.assertEqual(recs[0]["advice"]["after"], AFTER)
        self.assertIn("Goal: make checkout faster", once(self.cfg, 130, 40).replace("│", ""))
        with open(os.path.join(self.cfg, "sent.log"), encoding="utf-8") as f: sent = f.read()
        self.assertIn("Z01", sent); self.assertNotIn("Z02", sent)                  # only the chosen prompt was sent
        self.assertIn("Never ask for it again", sent)                               # the paste-marker rule is part of the request

    def test_a_failure_is_recorded_so_the_panel_can_say_why(self):
        self.job(self.key, FAKE_MODE="fail")
        with open(os.path.join(self.cfg, "coach", "rewrites.jsonl"), encoding="utf-8") as f: rec = json.loads(f.readline())
        self.assertEqual(rec["key"], self.key); self.assertIn("boom", rec["error"])
        self.assertIn("Claude's analysis failed", flat(once(self.cfg, 130, 40)))

    def test_unknown_keys_and_opted_out_projects_never_reach_claude(self):
        self.assertEqual(self.job("123.0:deadbeefdead", FAKE_JSON=self.ADV).returncode, 0)
        os.makedirs(os.path.join(self.cfg, "coach"), exist_ok=True)
        with open(os.path.join(self.cfg, "coach", "llm-off.txt"), "w") as f: f.write("p\n")
        self.job(self.key, FAKE_JSON=self.ADV)
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "sent.log")))


class AnalysisContext(Base):
    ADV = json.dumps(ADVICE)

    def test_only_the_last_three_earlier_prompts_of_the_same_conversation_are_context(self):
        rows = [("other", "p", "OTHERSESSION write the invoice report for me today"), ("now", "p", "EARLIERONE build the landing page for shoes"),
                ("now", "D:/w/secret", "SECRETPROMPT the confidential ledger migration plan"), ("now", "p", "EARLIERTWO make the hero section darker please"),
                ("now", "p", "EARLIERTHREE add a size guide below the products"), ("now", "p", "EARLIERFOUR now do the same for the second page"),
                ("now", "p", "TARGETPROMPT and also make it work on mobile too")]
        history(self.cfg, rows)
        os.makedirs(os.path.join(self.cfg, "coach"), exist_ok=True)
        with open(os.path.join(self.cfg, "coach", "llm-off.txt"), "w") as f: f.write("secret\n")
        r = run(self.cfg, "coach.py", "--bg-rewrite", "--key", key_for(6, rows[6][2]), FAKE_JSON=self.ADV)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.cfg, "sent.log"), encoding="utf-8") as f: sent = f.read()
        self.assertIn("EARLIER PROMPTS IN THIS CONVERSATION", sent)
        for want in ("EARLIERTWO", "EARLIERTHREE", "EARLIERFOUR", "TARGETPROMPT"): self.assertIn(want, sent)
        for never in ("EARLIERONE", "OTHERSESSION", "SECRETPROMPT"): self.assertNotIn(never, sent)   # 4th back, another conversation, opted out

    def test_a_prose_answer_is_retried_automatically_and_the_panel_gets_the_result(self):
        history(self.cfg, [("now", "p", "TARGETPROMPT make the checkout faster for every customer please")])
        r = run(self.cfg, "coach.py", "--bg-rewrite", "--key", key_for(0, "TARGETPROMPT make the checkout faster for every customer please"),
                FAKE_JSON=self.ADV, FAKE_BAD_ONCE=os.path.join(self.cfg, "bad-once"))
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.cfg, "sent.log"), encoding="utf-8") as f: self.assertEqual(f.read().count("====="), 2)
        self.assertIn("Goal: make checkout faster", flat(once(self.cfg, 120, 40)))


class CoachCommand(Base):
    def test_coach_prints_one_clean_block_and_copies_only_when_asked(self):
        history(self.cfg, [("now", "p", VAGUE)])
        out_file = os.path.join(self.cfg, "clip.bin")
        env = dict(FAKE_JSON=json.dumps(ADVICE), COACHLINE_CLIPBOARD=f'"{PY}" "{SINK}"', CLIP_OUT=out_file)
        r = run(self.cfg, "coach.py", "--coach", **env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.count("ENHANCED PROMPT"), 1)
        self.assertNotIn("AFTER:", r.stdout)                                   # not printed twice
        self.assertIn("Goal: make checkout faster [Pasted text #1 +28 lines].", r.stdout)
        self.assertFalse(os.path.exists(out_file))                             # no --copy, no clipboard write
        r = run(self.cfg, "coach.py", "--coach", "--copy", **env)
        self.assertIn("copied to your clipboard", r.stdout)
        with open(out_file, "rb") as f: self.assertEqual(f.read().decode("utf-8"), AFTER)


class Clipboard(unittest.TestCase):
    def test_override_command_receives_the_text_and_failure_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "c.bin"); old = {k: os.environ.get(k) for k in ("COACHLINE_CLIPBOARD", "CLIP_OUT")}
            try:
                os.environ["COACHLINE_CLIPBOARD"] = f'"{PY}" "{SINK}"'; os.environ["CLIP_OUT"] = out
                self.assertEqual(coach.copy_text("a\nb \u2192 c"), "override")
                with open(out, "rb") as f: self.assertEqual(f.read().decode("utf-8"), "a\nb \u2192 c")
                os.environ["COACHLINE_CLIPBOARD"] = f'"{PY}" -c "import sys; sys.exit(3)"'
                self.assertIsNone(coach.copy_text("x"))
            finally:
                for k, v in old.items():
                    if v is None: os.environ.pop(k, None)
                    else: os.environ[k] = v

    def test_clip_exe_gets_utf16_without_a_byte_order_mark(self):
        """Regression: a BOM was copied as a stray U+FEFF at the start of every pasted prompt."""
        seen = {}
        class Done:
            returncode = 0
        def fake_run(argv, input=None, **kw): seen["argv"], seen["input"] = argv, input; return Done()
        real = (coach.subprocess.run, coach.shutil.which, coach.os.name, os.environ.pop("COACHLINE_CLIPBOARD", None))
        try:
            coach.subprocess.run = fake_run
            coach.shutil.which = lambda n: "C:/Windows/System32/clip.exe" if n == "clip.exe" else None
            coach.os.name = "posix"                                             # the WSL case: no Win32 API, clip.exe via interop
            self.assertEqual(coach.copy_text("caf\u00e9 \u2192 ok"), "clip.exe")
        finally:
            coach.subprocess.run, coach.shutil.which, coach.os.name = real[:3]
            if real[3] is not None: os.environ["COACHLINE_CLIPBOARD"] = real[3]
        self.assertEqual(seen["input"], "caf\u00e9 \u2192 ok".encode("utf-16-le"))
        self.assertFalse(seen["input"].startswith(b"\xff\xfe"))

    @unittest.skipUnless(os.name == "nt" and os.environ.get("COACHLINE_TEST_REAL_CLIPBOARD"),
                         "touches the real Windows clipboard; only CI sets COACHLINE_TEST_REAL_CLIPBOARD, never run it on a machine whose clipboard you care about")
    def test_the_real_windows_clipboard_gets_exact_text_with_no_bom(self):
        import base64

        def ps(cmd):
            r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=60)
            return r.returncode, r.stdout.decode("ascii", "ignore").strip()          # everything crosses as base64 or digits: encoding-proof

        # Read the current clipboard as base64. If that is not perfectly reliable, do not touch the clipboard at all.
        rc, prev_b64 = ps("$c = Get-Clipboard -Raw; if ($null -eq $c) { 'EMPTY' } else { [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($c)) }")
        if rc != 0 or not prev_b64: self.skipTest("cannot read the current clipboard reliably; leaving it alone")
        os.environ.pop("COACHLINE_CLIPBOARD", None)
        try:
            method = coach.copy_text("Goal: caf\u00e9 \u2192 ok\nDone when: it works")
            if method is None: self.skipTest("no clipboard available in this session")
            rc, codes = ps("$c = Get-Clipboard -Raw; ($c.ToCharArray() | % { [int]$_ }) -join ','")
            self.assertEqual(codes.split(",")[:4], ["71", "111", "97", "108"])      # 'Goal': the first character is not U+FEFF (65279)
            self.assertNotIn("65279", codes.split(","))
            rc, got = ps("[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((Get-Clipboard -Raw)))")
            self.assertEqual(base64.b64decode(got).decode("utf-8").replace("\r\n", "\n").strip(), "Goal: caf\u00e9 \u2192 ok\nDone when: it works")
        finally:  # put back exactly what was there before (or clear it only if it really was empty)
            if prev_b64 == "EMPTY": ps("Set-Clipboard -Value $null")
            else: ps("Set-Clipboard -Value ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + prev_b64 + "')))")


if __name__ == "__main__":
    unittest.main()
