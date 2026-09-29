import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach, launch, watch  # noqa: E402

PY, W = "/usr/bin/python3", "/p/watch.py"


class Plan(unittest.TestCase):
    def test_tmux_splits_the_current_window_and_keeps_focus(self):
        a = launch.plan("Linux", {"TMUX": "/tmp/tmux-1/default,1,0", "CLAUDE_CONFIG_DIR": "/c"}, PY, W, which=lambda x: "/usr/bin/" + x)
        self.assertEqual(a[:5], ["tmux", "split-window", "-h", "-d", "-l"])
        self.assertIn("CLAUDE_CONFIG_DIR=/c", a)
        self.assertEqual(a[-1], f"{PY} {W}")

    def test_windows_terminal_splits_and_returns_focus(self):
        a = launch.plan("Windows", {"WT_SESSION": "abc"}, "C:/py/python.exe", "C:/x y/watch.py", which=lambda x: "wt.exe")
        self.assertEqual(a[:5], ["wt.exe", "-w", "0", "split-pane", "-V"])
        self.assertEqual(a[-3:], [";", "move-focus", "left"])
        self.assertIn("C:/x y/watch.py", a)                        # a path with a space stays one argument

    def test_windows_elsewhere_opens_a_console_window(self):
        a = launch.plan("Windows", {}, "C:/py/python.exe", "C:/w/watch.py", which=lambda x: None)
        self.assertEqual(a, ["C:/py/python.exe", "C:/w/watch.py"])        # spawn() gives it a new console; no cmd/start shim

    def test_macos_uses_terminal_app_and_escapes_quotes(self):
        a = launch.plan("Darwin", {}, "/opt/my py/python3", "/w/watch.py", which=lambda x: None)
        self.assertEqual(a[:2], ["osascript", "-e"])
        self.assertIn('tell application "Terminal" to do script', a[2])
        self.assertIn("'/opt/my py/python3'", a[2])

    def test_linux_needs_a_display_and_a_known_terminal(self):
        have = lambda name: (lambda x: "/usr/bin/" + x if x == name else None)
        self.assertEqual(launch.plan("Linux", {"DISPLAY": ":0"}, PY, W, which=have("gnome-terminal"))[:2], ["gnome-terminal", "--"])
        self.assertEqual(launch.plan("Linux", {"WAYLAND_DISPLAY": "w"}, PY, W, which=have("konsole"))[:2], ["konsole", "-e"])
        self.assertIsNone(launch.plan("Linux", {}, PY, W, which=have("gnome-terminal")))         # headless: nothing to open
        self.assertIsNone(launch.plan("Linux", {"DISPLAY": ":0"}, PY, W, which=lambda x: None))


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

    def run_main(self, *argv):
        return launch.main(list(argv), system="Windows", env={}, opener=self.opened.append)

    def test_auto_does_nothing_until_you_opt_in(self):
        self.assertEqual(self.run_main("--auto"), 0)
        self.assertEqual(self.opened, [])

    def test_opts_in_opens_once_and_never_a_second_panel(self):
        coach.set_setting("auto_open_watch", True)
        self.run_main("--auto"); self.assertEqual(len(self.opened), 1)
        self.run_main("--auto"); self.assertEqual(len(self.opened), 1)      # a session starting right behind it: launch lock
        os.remove(launch.LOCK); watch.beat.__defaults__[0][0] = 0           # the panel is now up and beating
        with open(coach.ALIVE, "w") as f: f.write("x")
        self.run_main("--auto"); self.assertEqual(len(self.opened), 1)      # heartbeat means already open
        os.utime(coach.ALIVE, (0, 0))                                       # heartbeat gone stale: the panel was closed
        self.run_main("--auto"); self.assertEqual(len(self.opened), 2)

    def test_manual_launch_works_without_opt_in_and_reports_problems(self):
        self.assertEqual(self.run_main(), 0); self.assertEqual(len(self.opened), 1)
        os.remove(launch.LOCK)
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(launch.main([], system="Linux", env={}, opener=self.opened.append), 1)   # headless Linux: tells you, exit 1
        self.assertIn("no terminal launcher found", out.getvalue())
        self.assertEqual(launch.main(["--auto"], system="Linux", env={}, opener=self.opened.append), 0)  # ...but a hook never fails

    def test_opener_failure_never_breaks_a_session_start(self):
        coach.set_setting("auto_open_watch", True)
        def boom(_a): raise OSError("no terminal")
        self.assertEqual(launch.main(["--auto"], system="Windows", env={}, opener=boom), 0)

    def test_the_panel_writes_the_heartbeat_the_launcher_reads(self):
        self.assertFalse(coach.panel_alive())
        watch.beat.__defaults__[0][0] = 0; watch.beat()
        self.assertTrue(coach.panel_alive())


class SetupSwitches(unittest.TestCase):
    def run_setup(self, cfg, *args):
        env = {**os.environ, "CLAUDE_CONFIG_DIR": cfg, "PYTHONIOENCODING": "utf-8"}
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "setup.py"), *args], capture_output=True, text=True, encoding="utf-8", env=env)

    def read(self, p):
        with open(p, encoding="utf-8") as f: return json.load(f)

    def test_auto_open_and_advisor_switches(self):
        with tempfile.TemporaryDirectory() as cfg:
            self.assertEqual(self.run_setup(cfg).returncode, 0)
            self.assertEqual(self.run_setup(cfg, "--auto-open", "on").returncode, 0)
            self.assertTrue(self.read(os.path.join(cfg, "coach", "config.json"))["auto_open_watch"])
            self.assertEqual(self.run_setup(cfg, "--advisor", "on").returncode, 0)
            self.assertEqual(self.read(os.path.join(cfg, "settings.json"))["statusLine"]["refreshInterval"], 10)
            self.assertTrue(self.read(os.path.join(cfg, "coach", "config.json"))["auto_rewrite"])
            self.run_setup(cfg, "--auto-rewrite", "off")                       # the old name still works
            self.assertNotIn("refreshInterval", self.read(os.path.join(cfg, "settings.json"))["statusLine"])
            self.assertFalse(self.read(os.path.join(cfg, "coach", "config.json"))["auto_rewrite"])
            self.assertTrue(self.read(os.path.join(cfg, "coach", "config.json"))["auto_open_watch"])   # independent switches
            self.assertNotEqual(self.run_setup(cfg, "--auto-open", "maybe").returncode, 0)

    def test_the_session_start_hook_runs_the_launcher(self):
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f: d = json.load(f)
        cmds = [h["command"] for h in d["hooks"]["SessionStart"][0]["hooks"]]
        self.assertTrue(any("launch.py" in c and "--auto" in c for c in cmds))
        self.assertTrue(any("setup.py" in c and "--refresh" in c for c in cmds))


if __name__ == "__main__":
    unittest.main()
