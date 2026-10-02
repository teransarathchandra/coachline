import json, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach, memory  # noqa: E402


def it(n, url=None):
    return {"name": f"Tool{n}", "kind": "tool", "why": "w", "url": url or f"https://www.Example.com/t{n}/"}


class Memory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.saved = coach.STATE; coach.STATE = os.path.join(self.tmp.name, "coach")
        self.file = os.path.join(coach.STATE, "suggestions.json")

    def tearDown(self):
        coach.STATE = self.saved; self.tmp.cleanup()

    def test_item_id_ignores_scheme_case_www_and_trailing_slash(self):
        self.assertEqual(memory.item_id({"url": "https://www.Example.com/T1/"}), "example.com/t1")
        self.assertEqual(memory.item_id({"url": "https://example.com/t1"}), "example.com/t1")
        self.assertEqual(memory.item_id({"name": "  WCAG ", "url": ""}), "wcag")

    def test_an_item_is_shown_with_at_most_two_prompts(self):
        items = [it(1), it(2)]
        self.assertEqual(len(memory.pick(items, key="k1")), 2)
        self.assertEqual(len(memory.pick(items, key="k2")), 2)
        self.assertEqual(memory.pick(items, key="k3"), [])
        self.assertEqual(len(memory.pick(items, key="k1")), 2)                 # the same prompt again does not count twice
        self.assertEqual([i["name"] for i in memory.pick([it(3)], key="k3")], ["Tool3"])

    def test_picking_without_a_key_records_nothing(self):
        for _ in range(3): memory.pick([it(1)])
        self.assertEqual(len(memory.pick([it(1)], key="k1")), 1)

    def test_dismissed_and_adopted_items_are_never_suggested_again(self):
        self.assertTrue(memory.mark(memory.item_id(it(1)), "dismissed"))
        self.assertTrue(memory.mark(memory.item_id(it(2)), "adopted"))
        self.assertEqual([i["name"] for i in memory.pick([it(1), it(2), it(3)], key="k1")], ["Tool3"])
        self.assertEqual(memory.statuses(), {"example.com/t1": "dismissed", "example.com/t2": "adopted"})
        self.assertFalse(memory.mark("example.com/t1", "maybe")); self.assertFalse(memory.mark("", "dismissed"))

    def test_bad_fields_inside_an_item_never_break_picking(self):
        os.makedirs(coach.STATE, exist_ok=True)
        with open(self.file, "w") as f:
            json.dump({"items": {"example.com/t1": {"shown": None}, "example.com/t2": {"shown": "abc"}, "example.com/t3": {"shown": 5, "ts": "x"}}}, f)
        self.assertEqual(len(memory.pick([it(1), it(2), it(3)], key="k1")), 3)
        self.assertEqual(len(memory.pick([it(1), it(2), it(3)])), 3)

    def test_the_limit_caps_what_is_picked(self):
        self.assertEqual(len(memory.pick([it(n) for n in range(8)], key="k1")), 4)

    def test_a_broken_or_huge_file_never_breaks_picking(self):
        os.makedirs(coach.STATE, exist_ok=True)
        with open(self.file, "w") as f: f.write("{broken")
        self.assertEqual(len(memory.pick([it(1)], key="k1")), 1)
        with open(self.file, "w") as f: json.dump({"items": {"x": "not a dict", "example.com/t1": ["nor this"]}}, f)
        self.assertEqual(len(memory.pick([it(1)], key="k2")), 1)
        self.assertEqual(memory.statuses(), {})
        memory.mark("keep.me/x", "dismissed")
        memory.pick([it(n) for n in range(600)], key="k9", limit=600)
        with open(self.file) as f: stored = json.load(f)["items"]
        self.assertLessEqual(len(stored), memory.MAX_KEEP); self.assertEqual(stored["keep.me/x"]["status"], "dismissed")   # choices are kept


if __name__ == "__main__":
    unittest.main()
