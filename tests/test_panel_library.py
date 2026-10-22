"""The Library in the standalone panel (Windows Terminal, /coach watch): l opens it; c copies a saved prompt, x forgets it, Esc goes back."""
import json, os, unittest

from test_watch import Base, history, plain, ADVICE, VAGUE, SOLID
import watch

A = "add pagination to the orders table with 25 rows per page and keep the current sort order"
B = "write a migration that adds an index on the created_at column of the events table in postgres"
EMPTY = "Prompts that worked first time land here: none yet in this project."


class Fake:
    def __init__(self):
        self.copied, self.used, self.forgotten = [], [], []

    def copy(self, text): self.copied.append(text); return "fake clipboard"
    def used_saved(self, i): self.used.append(i); return True
    def forget_saved(self, i): self.forgotten.append(i); return True


class LibraryMode(Base):
    def saved(self, *texts):
        items = [{"id": f"id{n}", "text": t, "project": "p", "stack": [], "ts": 100 - n, "uses": 0, "off": False} for n, t in enumerate(texts)]
        self.write_json("library.json", {"items": items})

    def test_l_opens_it_and_c_copies_the_chosen_prompt(self):
        history(self.cfg, [("s", "p", SOLID)]); self.analyse(0, SOLID); self.saved(A, B)
        io = Fake()
        frames = self.drive(["l", "j", "c"], io=io)
        self.assertIn("Library", plain(frames[1])); self.assertIn("add pagination", plain(frames[1])); self.assertIn("write a migration", plain(frames[1]))
        self.assertEqual((io.copied, io.used), ([B], ["id1"]))

    def test_x_forgets_and_esc_goes_back_to_the_card(self):
        history(self.cfg, [("s", "p", SOLID)]); self.analyse(0, SOLID); self.saved(A, B)
        io = Fake()
        frames = self.drive(["l", "x", "\x1b", "c"], io=io)
        self.assertEqual(io.forgotten, ["id0"])
        self.assertNotIn("add pagination", plain(frames[2]))                          # gone from the list at once
        self.assertEqual(io.copied, [ADVICE["after"]])                                # Esc: c copies the enhanced prompt again

    def test_an_empty_library_says_what_lands_there(self):
        history(self.cfg, [("s", "p", VAGUE)])
        frames = self.drive(["l"], io=Fake())
        self.assertIn(EMPTY, " ".join(plain(frames[-1]).split()))

    def test_a_narrow_pane_keeps_the_library_keys(self):
        history(self.cfg, [("s", "p", SOLID)]); self.saved(A)
        frame = plain(self.drive(["l"], W=40, H=14, io=Fake())[-1])          # under 40 columns l and Esc still work, unnamed
        foot = frame.splitlines()[-1]
        self.assertIn("c copy", foot); self.assertIn("l back", foot); self.assertIn("q quit", foot)

    def test_a_click_chooses_a_saved_prompt(self):
        history(self.cfg, [("s", "p", SOLID)]); self.saved(A, B)
        st = watch.build(self.path); ui = watch.new_ui(); io = Fake()
        watch.handle(ui, st, "l", io); watch.render(st, ui, 100, 30)
        row, c0, _c1, act = next(h for h in ui["hits"] if h[3] == "lib:1")
        watch.handle(ui, st, ("M", 0, c0 + 1, row + 1, True), io)                      # a left click on B's line
        watch.handle(ui, st, "c", io)
        self.assertEqual(io.copied, [B])

    def test_the_chosen_prompt_stays_on_screen(self):
        history(self.cfg, [("s", "p", SOLID)]); self.saved(*[f"{A} number {n:02d}" for n in range(30)])
        frames = self.drive(["l"] + ["j"] * 25, W=100, H=20, io=Fake())
        self.assertIn("› " + A[:40], plain(frames[-1]))

    def test_the_choice_follows_the_prompt_when_the_list_reorders(self):
        history(self.cfg, [("s", "p", SOLID)]); self.saved(A, B)
        st = watch.build(self.path); ui = watch.new_ui(); io = Fake()
        for k in ("l", "j"): watch.handle(ui, st, k, io)
        watch.render(st, ui, 100, 30)
        st["library"].reverse()                                          # a reload sorted B first (it was used)
        watch.render(st, ui, 100, 30); watch.handle(ui, st, "x", io)
        self.assertEqual(io.forgotten, ["id1"])

    def test_a_change_to_the_library_redraws_the_panel(self):
        history(self.cfg, [("s", "p", SOLID)]); self.saved(A)
        before = watch.signature(watch.build(self.path))
        self.saved(A, B)
        self.assertNotEqual(before, watch.signature(watch.build(self.path)))

    def test_mouse_key_and_wheel_in_the_library(self):
        history(self.cfg, [("s", "p", SOLID)]); self.saved(A, B)
        st = watch.build(self.path); ui = watch.new_ui(); io = Fake()
        watch.handle(ui, st, "l", io); watch.render(st, ui, 100, 30)
        watch.handle(ui, st, "m", io); self.assertFalse(ui["mouse"])
        lr = ui["list_rows"]; watch.handle(ui, st, ("M", 65, 5, lr[0] + 1, True), io)    # wheel down over the prompt list
        self.assertEqual(ui["lsel"], 0)

    def test_the_footer_names_the_library_key(self):
        history(self.cfg, [("s", "p", SOLID)])
        self.assertIn("l library", plain(self.drive([], W=120, io=Fake())[-1]).splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
