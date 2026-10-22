"""Snapshot of every panel screen, plain and with colour. A change to how a screen looks shows up as a diff in tests/snapshots/.

  UPDATE_SNAPSHOTS=1 python -m unittest tests.test_snapshots     rewrite the snapshots after a deliberate change
"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_watch import VAGUE, Base, history, watch  # noqa: E402

SNAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")
WIDE = "これを直してください \U0001F680 ☀\ufe0f " * 6 + "please make the invoice page faster"


class Snapshots(Base):
    def setUp(self):
        super().setUp()
        self._stamp = watch.stamp; watch.stamp = lambda ts: "Jun 15 09:30"     # the clock and the time zone are not part of the look
        self._cmd = watch.coach.py_cmd; watch.coach.py_cmd = lambda *a: "python " + " ".join(a)   # nor where it is installed

    def tearDown(self):
        watch.stamp, watch.coach.py_cmd = self._stamp, self._cmd; super().tearDown()

    def screen(self, name, W, H, **ui_kw):
        st = watch.build(self.path); out = []
        for color in (False, True):
            ui = watch.new_ui(); ui.update(ui_kw)
            out.append("\n".join(watch.render(st, ui, W, H, color=color)).replace("\x1b", "␛"))
        got = (f"{name} {W}x{H}\n--- plain ---\n{out[0]}\n--- ansi (␛ = ESC) ---\n{out[1]}\n")
        path = os.path.join(SNAP, name + ".txt")
        if os.environ.get("UPDATE_SNAPSHOTS") or not os.path.exists(path):
            os.makedirs(SNAP, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f: f.write(got)
        with open(path, encoding="utf-8") as f: self.assertEqual(got, f.read(), f"{name} changed; UPDATE_SNAPSHOTS=1 if deliberate")

    def thread(self, n=6):
        history(self.cfg, [("now", "p", f"P{i:02d} " + VAGUE) for i in range(1, n + 1)])

    def test_empty(self):
        history(self.cfg, [])
        self.screen("empty", 100, 30)

    def test_local_hints_claude_off(self):
        self.thread(); self.screen("local-hints", 100, 30)

    def test_analysed_wide(self):
        self.thread(); self.analyse(5, "P06 " + VAGUE); self.screen("analysed-100", 100, 40)

    def test_analysed_medium(self):
        self.thread(); self.analyse(5, "P06 " + VAGUE); self.screen("analysed-60", 60, 30)

    def test_analysed_narrow(self):
        self.thread(); self.analyse(5, "P06 " + VAGUE); self.screen("analysed-30", 30, 12)

    def test_too_narrow(self):
        self.thread(); self.screen("too-narrow", 22, 12)

    def test_working(self):
        self.write_json("config.json", {"panel_ai": True}); self.thread(); self.screen("working", 80, 24)

    def test_failed(self):
        self.thread(); self.add_record(watch_key(5), text="", error="usage limit reached"); self.screen("failed", 80, 24)

    def test_full_view(self):
        self.thread(); self.analyse(5, "P06 " + VAGUE); self.screen("full-view", 80, 30, detail=True)

    def test_patterns_expanded(self):
        self.thread()
        self.write_json("learned.json", {"generated": "2026-09-30", "prompts": 99, "requests": [{"name": "carefully-things", "keywords": ["carefully"], "count": 4}], "mistakes": []})
        self.screen("patterns", 80, 30, patterns=True)

    def test_messages(self):
        self.thread(); self.analyse(5, "P06 " + VAGUE)
        self.screen("message-ok", 80, 24, msg="copied the enhanced prompt (60 characters) via clip.exe", msg_kind="ok")
        self.screen("message-bad", 80, 24, msg="could not save that choice (see /coach doctor)", msg_kind="bad")
        self.screen("message-info", 80, 24, msg="asking Claude in the background (about 20 seconds); the panel updates by itself")

    def test_wide_glyphs(self):
        history(self.cfg, [("now", "p", WIDE), ("now", "p", WIDE + " again")])
        self.screen("wide-glyphs", 44, 20)


def watch_key(i):
    from test_watch import key_for
    return key_for(i, f"P{i + 1:02d} " + VAGUE)


if __name__ == "__main__":
    unittest.main()
