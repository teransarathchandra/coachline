"""Direction A's accent and the panel's four motions: shimmer, reveal, Copied flash, quality meter. All of it off with one switch."""
import os, sys, time, unittest
from unittest import mock

from test_watch import Base, history, plain, ADVICE, SOLID
import coach, watch


class Switch(Base):
    def test_motion_off_under_no_color_ssh_and_setting(self):
        self.assertTrue(coach.motion_on({}))
        self.assertFalse(coach.motion_on({"NO_COLOR": "1"}))
        self.assertFalse(coach.motion_on({"SSH_TTY": "/dev/pts/0"}))
        self.assertFalse(coach.motion_on({"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}))
        coach.set_setting("motion", False)
        self.assertFalse(coach.motion_on({}))

    def test_truecolor_detection(self):
        self.assertTrue(watch.truecolor({"COLORTERM": "truecolor"}))
        self.assertTrue(watch.truecolor({"WT_SESSION": "x"}))
        self.assertFalse(watch.truecolor({"TERM": "xterm"}))

    def test_setup_motion_flag(self):
        import setup
        with mock.patch("builtins.print"): setup.main(["--motion", "off"])
        self.assertIs(coach.setting("motion"), False)


class Frames(Base):
    def working(self):
        history(self.cfg, [("s", "p", SOLID)])
        self.write_json("config.json", {"panel_ai": True})
        st = watch.build(self.path); ui = watch.new_ui()
        ui["pending"][st["entries"][-1]["key"]] = time.time()
        return st, ui

    def poll(self, motion):
        st, ui = self.working(); timeouts = []
        keys = iter([None, None, None])
        def next_key(t):
            timeouts.append(t); return next(keys, "q")
        watch.loop(next_key, lambda rows: None, lambda: (100, 30), lambda: st, motion=motion,
                   work=lambda s, u: u["pending"].update(ui["pending"]))
        return timeouts

    def test_no_motion_no_redraw_loop(self):
        self.assertTrue(all(t == 0.25 for t in self.poll(motion=False)), self.poll(motion=False))
        self.assertIn(0.1, self.poll(motion=True))

    def test_working_header_is_static_text_without_motion(self):
        st, ui = self.working()
        head = plain(watch.render(st, ui, 100, 30)[0])
        self.assertIn("… Claude working", head)

    def test_shimmer_moves_the_accent(self):
        st, ui = self.working(); ui["motion"] = True
        a = watch.render(st, ui, 100, 30)[0]; ui["tick"] += 1; b = watch.render(st, ui, 100, 30)[0]
        self.assertNotEqual(a, b); self.assertEqual(plain(a), plain(b))
        self.assertIn(f"\033[{watch.CODE['accent']}m", a)

    def analysed(self):
        history(self.cfg, [("s", "p", SOLID)]); self.analyse(0, SOLID)
        return watch.build(self.path)

    def test_reveal_completes_in_150ms(self):
        history(self.cfg, [("s", "p", SOLID)])
        ui = watch.new_ui(); ui["motion"] = True; ui["now"] = 100.0
        watch.render(watch.build(self.path), ui, 100, 40)           # seen: nothing analysed yet
        self.analyse(0, SOLID); st = watch.build(self.path)
        first = watch.render(st, ui, 100, 40)
        ui["now"] = 100.16; done = watch.render(st, ui, 100, 40)
        static = watch.render(st, {**watch.new_ui(), "seen": ui["seen"]}, 100, 40)
        self.assertLess(sum(1 for r in first if r.strip()), sum(1 for r in done if r.strip()))
        self.assertEqual(done, static)
        self.assertFalse(ui["animating"])

    def test_no_reveal_for_analyses_already_there(self):
        st = self.analysed(); ui = watch.new_ui(); ui["motion"] = True; ui["now"] = 100.0
        self.assertEqual(watch.render(st, ui, 100, 40), watch.render(st, watch.new_ui(), 100, 40))

    def test_copied_flash_for_200ms(self):
        st = self.analysed(); key = st["entries"][-1]["key"]
        ui = watch.new_ui(); ui["motion"] = True; ui["now"] = 100.0; ui["copied"][key] = 100.0
        with mock.patch("time.time", return_value=100.0): lit = "\n".join(watch.render(st, ui, 100, 40))
        ui["now"] = 100.3
        with mock.patch("time.time", return_value=100.3): after = "\n".join(watch.render(st, ui, 100, 40))
        self.assertIn(f"\033[{watch.CODE['flash']}m", lit); self.assertNotIn(f"\033[{watch.CODE['flash']}m", after)
        self.assertIn("✓ Copied", plain(after))

    def test_meter_cells(self):
        self.assertLessEqual(watch.meter("fix it").count("▰"), 1)
        self.assertGreaterEqual(watch.meter(SOLID).count("▰"), 4)
        self.assertEqual(len(watch.meter("fix it")), 5)
        history(self.cfg, [("s", "p", SOLID)])
        self.assertIn(watch.meter(SOLID), plain("\n".join(watch.render(watch.build(self.path), watch.new_ui(), 100, 40))))

    def test_still_panel_redraws_on_every_reload(self):
        st, _ui = self.working(); frames = []; t = [0.0]
        def clock(): t[0] += 1.0; return t[0]
        keys = iter([None] * 4)
        watch.loop(lambda _t: next(keys, "q"), frames.append, lambda: (100, 30), lambda: st, clock=clock, reload_every=2.0, motion=False)
        self.assertGreater(len(frames), 1)          # a queued prompt that timed out must leave "Claude working" without a key press

    def test_sixteen_colour_fallbacks(self):
        self.assertEqual((watch.CODE["brand"], watch.CODE["accent"]), ("1;97;44", "94"))     # the spec's fallbacks
        self.assertNotIn("41", watch.CODE["flash"].split(";"))                               # red means failed here, never Copied

    def test_slow_frames_turn_motion_off(self):
        st, _ui = self.working(); seen = {}
        keys = iter([None] * 5)
        def write(rows): time.sleep(0.05)
        def next_key(t): return next(keys, "q")
        def work(s, u): seen["ui"] = u
        watch.loop(next_key, write, lambda: (100, 30), lambda: st, motion=True, work=work, reload_every=0)
        self.assertFalse(seen["ui"]["motion"])


if __name__ == "__main__":
    unittest.main()
