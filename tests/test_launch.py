import contextlib, io, json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach, launch, watch  # noqa: E402

PY, W = "/usr/bin/python3", "/p/watch.py"
HAVE = lambda x: "/usr/bin/" + x
NONE = lambda x: None


class Plan(unittest.TestCase):
    def test_tmux_splits_the_current_window_and_keeps_focus(self):
        a = launch.plan("Linux", {"TMUX": "/tmp/tmux-1/default,1,0", "CLAUDE_CONFIG_DIR": "/c"}, PY, W, which=HAVE)
        self.assertEqual(a[:5], ["tmux", "split-window", "-h", "-d", "-l"])
        self.assertIn("CLAUDE_CONFIG_DIR=/c", a)
        self.assertEqual(a[-1], f"{PY} {W}")

    def test_windows_terminal_splits_and_returns_focus(self):
        a = launch.plan("Windows", {"WT_SESSION": "abc"}, "C:/py/python.exe", "C:/x y/watch.py", which=lambda x: "wt.exe")
        self.assertEqual(a[:5], ["wt.exe", "-w", "0", "split-pane", "-V"])
        self.assertEqual(a[-3:], [";", "move-focus", "left"])
        self.assertIn("C:/x y/watch.py", a)                        # a path with a space stays one argument

    def test_only_real_splits_are_used_never_a_separate_window(self):
        self.assertIsNone(launch.plan("Windows", {}, "C:/py/python.exe", "C:/w/watch.py", which=NONE))              # plain console
        self.assertIsNone(launch.plan("Windows", {"WT_SESSION": "abc"}, "C:/py/python.exe", "C:/w/watch.py", which=NONE))   # wt.exe missing
        self.assertIsNone(launch.plan("Darwin", {}, "/usr/bin/python3", "/w/watch.py", which=HAVE))                # no Terminal.app windows
        self.assertIsNone(launch.plan("Linux", {"DISPLAY": ":0"}, PY, W, which=HAVE))                              # no emulator windows
        self.assertIsNone(launch.plan("Linux", {"TMUX": "x"}, PY, W, which=NONE))                                   # tmux variable but no tmux


class Main(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); s = self.tmp.name
        self.saved = (coach.STATE, coach.USER_CFG, coach.ALIVE, launch.LOCK)
        coach.STATE, coach.USER_CFG = s, os.path.join(s, "config.json")
        coach.ALIVE, launch.LOCK = os.path.join(s, "watch.alive"), os.path.join(s, "watch.launching")
        self.opened = []

    def tearDown(self):
        coach.STATE, coach.USER_CFG, coach.ALIVE, launch.LOCK = self.saved
        self.tmp.cleanup()

    def run_main(self, *argv, env=None):
        return launch.main(list(argv), system="Windows", env=env if env is not None else {"WT_SESSION": "x"}, opener=self.opened.append, which=HAVE)

    def test_auto_does_nothing_until_you_opt_in(self):
        self.assertEqual(self.run_main("--auto"), 0)
        self.assertEqual(self.opened, [])

    def test_opts_in_splits_once_and_never_a_second_panel(self):
        coach.set_setting("auto_open_watch", True)
        self.run_main("--auto"); self.assertEqual(len(self.opened), 1)
        self.run_main("--auto"); self.assertEqual(len(self.opened), 1)      # a session starting right behind it: launch lock
        os.remove(launch.LOCK)
        with open(coach.ALIVE, "w") as f: f.write("x")                      # the panel is up and beating
        self.run_main("--auto"); self.assertEqual(len(self.opened), 1)
        os.utime(coach.ALIVE, (0, 0))                                       # heartbeat gone stale: the panel was closed
        self.run_main("--auto"); self.assertEqual(len(self.opened), 2)

    def test_where_it_cannot_split_it_stays_silent_for_hooks_and_prints_the_command_by_hand(self):
        coach.set_setting("auto_open_watch", True)
        self.assertEqual(self.run_main("--auto", env={}), 0)                # a hook never fails and never opens a window
        self.assertEqual(self.opened, [])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.run_main(env={}), 1)
        self.assertIn("cannot split a pane", out.getvalue()); self.assertIn("panel.py", out.getvalue())
        self.assertEqual(self.opened, [])

    def test_manual_launch_works_without_opt_in(self):
        self.assertEqual(self.run_main(), 0); self.assertEqual(len(self.opened), 1)

    def test_opener_failure_never_breaks_a_session_start(self):
        coach.set_setting("auto_open_watch", True)
        def boom(_a): raise OSError("no terminal")
        self.assertEqual(launch.main(["--auto"], system="Windows", env={"WT_SESSION": "x"}, opener=boom, which=HAVE), 0)

    def test_the_command_option_prints_a_short_stable_path_and_the_launcher_works(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(launch.main(["--command"]), 0)
        cmd = out.getvalue().strip()
        shim = os.path.join(coach.STATE, "panel.py")
        self.assertIn(shim.replace("\\", "/"), cmd.replace("\\", "/").strip('"'))
        with open(shim, encoding="utf-8") as f: body = f.read()
        self.assertIn(repr(launch.WATCH), body)                              # forwards to this version's watch.py
        with open(shim, "w") as f: f.write("# stale shim from an older plugin version\n")
        launch.ensure_shim()
        with open(shim, encoding="utf-8") as f: self.assertIn(repr(launch.WATCH), f.read())   # rewritten after an update

    def test_the_command_really_opens_the_panel(self):
        launch.ensure_shim()
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.tmp.name, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([sys.executable, os.path.join(coach.STATE, "panel.py"), "--once", "--width", "80", "--height", "12"],
                           capture_output=True, text=True, encoding="utf-8", env=env, input="")
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("this thread", r.stdout)


class SetupSwitches(unittest.TestCase):
    def run_setup(self, cfg, *args):
        env = {**os.environ, "CLAUDE_CONFIG_DIR": cfg, "PYTHONIOENCODING": "utf-8"}
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "setup.py"), *args], capture_output=True, text=True, encoding="utf-8", env=env, input="")

    def read(self, p):
        with open(p, encoding="utf-8") as f: return json.load(f)

    def test_the_switches_are_independent_and_old_names_still_work(self):
        with tempfile.TemporaryDirectory() as cfg:
            conf = os.path.join(cfg, "coach", "config.json")
            self.assertEqual(self.run_setup(cfg, "--panel-ai", "on").returncode, 0)
            self.assertTrue(self.read(conf)["panel_ai"])
            self.assertEqual(self.run_setup(cfg, "--auto-open", "on").returncode, 0)
            self.assertEqual(self.run_setup(cfg, "--discover", "on").returncode, 0)
            self.run_setup(cfg, "--advisor", "off")                                   # old name = --panel-ai
            c = self.read(conf)
            self.assertEqual((c["panel_ai"], c["auto_open_watch"], c["discover"]), (False, True, True))
            self.run_setup(cfg, "--auto-rewrite", "on")                               # the other old name
            self.assertTrue(self.read(conf)["panel_ai"])
            self.assertNotEqual(self.run_setup(cfg, "--auto-open", "maybe").returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(cfg, "settings.json")))      # switches never touch Claude Code's settings.json

    def test_the_refresh_hook_records_the_session_that_just_started(self):
        with tempfile.TemporaryDirectory() as cfg:
            env = {**os.environ, "CLAUDE_CONFIG_DIR": cfg, "PYTHONIOENCODING": "utf-8"}
            sf = os.path.join(cfg, "coach", "current-session.json")

            def hook(payload):                                                         # what Claude Code pipes to a SessionStart hook
                r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "setup.py"), "--refresh"], input=payload, capture_output=True, text=True, env=env)
                self.assertEqual(r.returncode, 0, r.stderr)                           # never fails a session start
            hook("not json"); hook(json.dumps({"session_id": "../../evil", "source": "startup"}))
            self.assertFalse(os.path.exists(sf))
            hook(json.dumps({"session_id": "abcd1234-aaaa-bbbb-cccc", "source": "startup", "cwd": "C:\\work"}))
            self.assertEqual(self.read(sf)["id"], "abcd1234-aaaa-bbbb-cccc")
            hook(json.dumps({"session_id": "zzzz9999-aaaa-bbbb-cccc", "source": "resume"}))
            self.assertEqual(self.read(sf)["id"], "abcd1234-aaaa-bbbb-cccc")           # a resume does not replace it

    def test_a_silent_open_stdin_never_blocks_a_session_start(self):
        with tempfile.TemporaryDirectory() as cfg:
            env = {**os.environ, "CLAUDE_CONFIG_DIR": cfg, "PYTHONIOENCODING": "utf-8"}
            p = subprocess.Popen([sys.executable, os.path.join(ROOT, "scripts", "setup.py"), "--refresh"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            try:
                self.assertEqual(p.wait(timeout=15), 0)                                # nobody writes or closes stdin: it gives up after about a second
            finally:
                if p.poll() is None: p.kill()
                for s in (p.stdin, p.stdout, p.stderr): s.close()

    def test_the_consent_text_says_what_is_sent(self):
        with tempfile.TemporaryDirectory() as cfg:
            out = self.run_setup(cfg, "--panel-ai", "on").stdout
            for want in ("no API key", "redacted", "90 days", "llm-off.txt", "setup.py --panel-ai off"):
                self.assertIn(want, out)

    def test_the_session_start_hook_runs_the_launcher_and_the_refresh(self):
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f: d = json.load(f)
        cmds = [h["command"] for h in d["hooks"]["SessionStart"][0]["hooks"]]
        self.assertTrue(any("launch.py" in c and "--auto" in c for c in cmds))
        self.assertTrue(any("setup.py" in c and "--refresh" in c for c in cmds))


if __name__ == "__main__":
    unittest.main()
