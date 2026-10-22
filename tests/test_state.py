"""coachline's own files under <config>/coach: written whole or not at all, stamped with a version, swept when stale."""
import glob, json, os, sys, tempfile, time, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach, discover, setup  # noqa: E402


def load(p):
    with open(p, encoding="utf-8") as f: return json.load(f)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); d = self.tmp.name
        self.state = os.path.join(d, "coach")
        self.saved = {k: getattr(coach, k) for k in ("STATE", "USER_CFG", "LEARNED", "REWRITES", "OFF", "ALIVE")}
        coach.STATE = self.state; coach.USER_CFG = os.path.join(self.state, "config.json")
        coach.LEARNED = os.path.join(self.state, "learned.json"); coach.REWRITES = os.path.join(self.state, "rewrites.jsonl")
        coach.OFF = os.path.join(self.state, "llm-off.txt"); coach.ALIVE = os.path.join(self.state, "watch.alive")
        self.saved_settings = setup.SETTINGS; setup.SETTINGS = os.path.join(d, "settings.json")
        os.makedirs(self.state)

    def tearDown(self):
        for k, v in self.saved.items(): setattr(coach, k, v)
        setup.SETTINGS = self.saved_settings
        self.tmp.cleanup()

    def put(self, name, text="x", age_days=0):
        p = os.path.join(self.state, name); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f: f.write(text)
        if age_days: t = time.time() - age_days * 86400; os.utime(p, (t, t))
        return p


class AtomicWrites(Base):
    def test_write_json_is_whole_or_absent(self):
        p = os.path.join(self.state, "x.json")
        with mock.patch("os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError): coach.write_json(p, {"a": 1})
        self.assertFalse(os.path.exists(p))
        self.assertEqual(glob.glob(os.path.join(self.state, "*.tmp")), [])

    def test_write_json_stamps_v(self):
        p = os.path.join(self.state, "x.json"); d = {"a": 1}
        coach.write_json(p, d)
        self.assertEqual(load(p), {"a": 1, "v": 1})
        self.assertEqual(d, {"a": 1})

    def test_settings_json_never_stamped(self):
        setup.write({"x": 1}); setup.write({"x": 1})
        self.assertEqual(load(setup.SETTINGS), {"x": 1})
        self.assertTrue(os.path.exists(setup.SETTINGS + ".coach-bak"))

    def test_config_and_learned_and_session_are_atomic(self):
        with mock.patch("os.replace", side_effect=OSError("no")):
            with self.assertRaises(OSError): coach.set_setting("motion", False)
            coach.record_session(json.dumps({"session_id": "abcdef12-3456", "source": "startup"}))   # silent on errors, never half-written
        self.assertFalse(os.path.exists(coach.USER_CFG))
        self.assertFalse(os.path.exists(coach.session_file()))

    def test_discover_cache_ignores_v(self):
        old = {"old": {"ts": time.time(), "items": [{"name": "A"}]}}
        discover._dump("discover-cache.json", old)
        with mock.patch.object(discover, "find", return_value=[]), mock.patch.object(discover, "verify_all", return_value=([], [])), \
             mock.patch.object(discover, "have_names", return_value=set()), mock.patch.object(discover, "paused_until", return_value=None):
            discover.for_advice({"task": "t", "summary": "s", "use": []}, fresh=True)
        cache = load(os.path.join(self.state, "discover-cache.json"))
        self.assertEqual(cache["v"], 1)
        self.assertEqual({k for k in cache if k != "v"} - {"old"}, {discover.topic_key({"task": "t", "summary": "s", "use": []}, ())})

    def test_write_json_retries_then_cleans_up(self):
        p = os.path.join(self.state, "x.json")
        with mock.patch("os.replace", side_effect=PermissionError("in use")), mock.patch("time.sleep"):
            with self.assertRaises(PermissionError): coach.write_json(p, {"a": 1})
        self.assertEqual(glob.glob(os.path.join(self.state, "*.tmp")), [])

    @unittest.skipUnless(hasattr(os, "symlink"), "no symlinks")
    def test_write_json_writes_through_a_symlink(self):
        real = os.path.join(self.tmp.name, "dotfiles-settings.json")
        with open(real, "w") as f: f.write("{}")
        try: os.symlink(real, setup.SETTINGS)
        except (OSError, NotImplementedError): self.skipTest("symlinks need privileges here")
        setup.write({"x": 1})
        self.assertTrue(os.path.islink(setup.SETTINGS)); self.assertEqual(load(real), {"x": 1})

    def test_v0_files_still_read(self):
        self.put("config.json", json.dumps({"panel_ai": False}))
        self.assertFalse(coach.ai_on())


class Sweep(Base):
    STALE = ["current-session-ab12.json", "watch-ab12.alive", "watch-ab12.launching", "pane-ab12.json", "pane-ab12.lock"]

    def test_sweep_removes_old_per_session_files(self):
        for n in self.STALE: self.put(n, age_days=8)
        self.assertEqual(sorted(coach.sweep()), sorted(self.STALE))
        self.assertEqual(os.listdir(self.state), [])

    def test_sweep_keeps_fresh_and_shared(self):
        self.put("watch-abc.alive")
        keep = ["watch.alive", "current-session.json", "watch.session", "config.json", "llm-off.txt", "watch.launching"]
        for n in keep: self.put(n, age_days=30)
        self.assertEqual(coach.sweep(), [])
        self.assertEqual(sorted(os.listdir(self.state)), sorted(keep + ["watch-abc.alive"]))

    def test_a_live_tabs_session_file_is_kept_however_old(self):
        self.put("current-session-t1.json", age_days=30); self.put("watch-t1.alive")      # the tab's panel beats: the session is in use
        self.put("current-session-t2.json", age_days=30)
        self.assertEqual(coach.sweep(), ["current-session-t2.json"])

    def test_rewrites_compacted_even_while_a_panel_is_open(self):
        p = self.put("rewrites.jsonl", "".join(json.dumps({"n": i}) + "\n" for i in range(5003))); self.put("watch-t1.alive")
        coach.sweep()
        with open(p, encoding="utf-8") as f: self.assertEqual(len(f.read().splitlines()), 5000)

    def test_rewrites_compaction_failure_leaves_no_tmp_and_the_log_whole(self):
        p = self.put("rewrites.jsonl", "".join(json.dumps({"n": i}) + "\n" for i in range(5003)))
        with mock.patch("os.replace", side_effect=PermissionError("in use")), mock.patch("time.sleep"):
            coach.sweep()
        self.assertEqual(glob.glob(os.path.join(self.state, "*.tmp")), [])
        with open(p, encoding="utf-8") as f: self.assertEqual(len(f.read().splitlines()), 5003)

    def test_rewrites_compacted_to_last_5000(self):
        p = self.put("rewrites.jsonl", "".join(json.dumps({"n": i}) + "\n" for i in range(5003)))
        coach.sweep()
        with open(p, encoding="utf-8") as f: lines = f.read().splitlines()
        self.assertEqual(len(lines), 5000); self.assertEqual(json.loads(lines[0]), {"n": 3})

    def test_short_rewrites_untouched(self):
        p = self.put("rewrites.jsonl", "".join(json.dumps({"n": i}) + "\n" for i in range(10)), age_days=2)
        before = os.path.getmtime(p); coach.sweep()
        self.assertEqual(os.path.getmtime(p), before)

    def test_refresh_survives_sweep_error(self):
        with mock.patch.object(coach, "sweep", side_effect=OSError("locked")), mock.patch.object(setup, "hook_json", return_value=""):
            setup.main(["--refresh"])

    def test_refresh_sweeps(self):
        self.put("watch-old.alive", age_days=8)
        with mock.patch.object(setup, "hook_json", return_value=""): setup.main(["--refresh"])
        self.assertFalse(os.path.exists(os.path.join(self.state, "watch-old.alive")))


class Forget(Base):
    def test_forget_all_keeps_settings_launcher_and_live_locks(self):
        keep = ["config.json", "llm-off.txt", "panel.py", "review.running", "watch-t1.launching"]
        for n in keep + ["rewrites.jsonl", "drafts/x/SKILL.md", "learned.json"]: self.put(n)
        coach.forget("all")
        self.assertEqual(sorted(os.listdir(self.state)), sorted(keep))

    def test_data_usage_counts_files_and_bytes(self):
        self.put("a.json", "12345"); self.put("drafts/x/SKILL.md", "123")
        self.assertEqual(coach.data_usage(), (2, 8))

    def test_forget_unknown_changes_nothing(self):
        from test_review import run
        with tempfile.TemporaryDirectory() as cfg:
            os.makedirs(os.path.join(cfg, "coach")); p = os.path.join(cfg, "coach", "rewrites.jsonl")
            with open(p, "w") as f: f.write("{}\n")
            r = run(cfg, "coach.py", "--forget", "bogus")
            self.assertEqual(r.returncode, 2, r.stderr); self.assertIn("usage: coach.py --forget all|outcomes|library", r.stdout + r.stderr)
            self.assertTrue(os.path.exists(p))
            r = run(cfg, "coach.py", "--forget", "all")
            self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("kept your settings and llm-off.txt", r.stdout)
            self.assertFalse(os.path.exists(p))

    def test_doctor_prints_data_line(self):
        from test_review import run, write_history
        with tempfile.TemporaryDirectory() as cfg:
            write_history(cfg, ["make the checkout page faster please"])
            os.makedirs(os.path.join(cfg, "coach"))
            with open(os.path.join(cfg, "coach", "rewrites.jsonl"), "w") as f: f.write("{}\n")
            out = run(cfg, "coach.py", "--doctor").stdout
            self.assertRegex(out, r"(?m)^ok   coachline data: 1 files?, ")
            self.assertIn("--forget all", out)


if __name__ == "__main__":
    unittest.main()
