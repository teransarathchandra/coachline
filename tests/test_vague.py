"""The local vagueness score, held to a fixed labelled set (tests/vague_cases.jsonl, made-up prompts, never real history).
A false "your prompt is vague" costs more than a miss, so precision has the floor; recall has one too, so never flagging can't pass."""
import json, os, sys, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach  # noqa: E402
from test_watch import SOLID  # noqa: E402

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vague_cases.jsonl"), encoding="utf-8") as f:
    CASES = [json.loads(l) for l in f if l.strip()]


class Vagueness(unittest.TestCase):
    def test_precision_floor(self):
        said = [(c, coach.vague(c["text"])) for c in CASES]
        tp = sum(1 for c, v in said if v and c["vague"]); fp = [c["text"] for c, v in said if v and not c["vague"]]
        fn = [c["text"] for c, v in said if not v and c["vague"]]
        precision = tp / max(tp + len(fp), 1); recall = tp / max(sum(c["vague"] for c in CASES), 1)
        msg = f"precision {precision:.2f} recall {recall:.2f}\n  wrongly vague: {fp}\n  missed: {fn}"
        self.assertGreaterEqual(precision, 0.9, msg)
        self.assertGreaterEqual(recall, 0.6, msg)

    def test_examples(self):
        self.assertTrue(coach.vague("fix it"))
        self.assertFalse(coach.vague(SOLID))
        self.assertFalse(coach.vague("[Pasted text #1 +40 lines] why does this fail"))
        self.assertTrue(coach.vague("P06 handle this carefully and make it good for all the customers we have"))   # digits in a label are no anchor

    def test_long_unbroken_text_is_fast(self):
        for t in ("ab-" * 20000, "a" * 50000, "x/" * 20000, "a.b-" * 12000):
            t0 = time.perf_counter(); coach.vagueness(t)
            self.assertLess(time.perf_counter() - t0, 0.5, t[:12])

    def test_cjk_words_are_counted(self):
        self.assertFalse(coach.vague("請求モジュールの税計算を地域ごとに見直して、現在の実装は拡張しにくいので読みやすく保守しやすい形に直してください"))
        self.assertTrue(coach.vague("直して"))

    def test_hint_names_what_is_missing(self):
        self.assertEqual(coach.hint_for("fix it"), "say what 'it' or 'this' is: a file, a function, an error")
        self.assertEqual(coach.hint_for("clean this up properly"), "replace 'best/properly/clean' with a rule you can check")
        self.assertEqual(coach.hint_for("write some tests"), "name a file, function, error or number")
        self.assertIsNone(coach.hint_for(SOLID)); self.assertIsNone(coach.hint_for(""))
        for c in CASES:
            if c["vague"]: self.assertIsNotNone(coach.hint_for(c["text"]), c["text"])

    def test_score_is_bounded(self):
        for c in CASES + [{"text": ""}, {"text": "x" * 5000}]:
            self.assertTrue(0.0 <= coach.vagueness(c["text"]) <= 1.0, c["text"][:40])


if __name__ == "__main__":
    unittest.main()
