import datetime as dt, json, os, sys, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach, discover  # noqa: E402
from test_review import run, write_history, read  # noqa: E402
from test_advisor import make_config  # noqa: E402

FAKE = os.path.join(ROOT, "tests", "fake_claude.py").replace("\\", "/")
PY = sys.executable.replace("\\", "/")
TODAY = dt.date.today()


def gh_json(full="acme/good-tool", desc="A good tool for designs", stars=1234, days_ago=30, archived=False):
    return json.dumps({"full_name": full, "description": desc, "stargazers_count": stars, "archived": archived,
                       "pushed_at": (TODAY - dt.timedelta(days=days_ago)).isoformat() + "T00:00:00Z"})


def getter(table):
    return lambda url: table.get(url, (404, ""))


API = "https://api.github.com/repos/"
HAVE = {"impeccable"}


class Safety(unittest.TestCase):
    def test_only_public_https_urls_pass(self):
        for good in ("https://github.com/a/b", "https://example.com/x", "https://8.8.8.8/"):
            self.assertTrue(discover.public_https(good), good)
        for bad in ("http://example.com", "https://localhost/x", "https://127.0.0.1/", "https://192.168.1.5/", "https://10.0.0.1/x",
                    "https://[::1]/", "https://user:pw@example.com/", "https://example.com:8443/", "https://intranet/", "https://a.local/", "ftp://x.com/", ""):
            self.assertFalse(discover.public_https(bad), bad)

    def test_terminal_escapes_and_control_characters_are_stripped(self):
        item = {"name": "Nice\x1b[31mTool\x07", "kind": "tool", "why": "great\x1b]0;evil\x07 stuff\x00", "url": "https://example.com/t", "install": "$ npm i\x1b[2J nice"}
        v, why = discover.verify_item(item, HAVE, getter({"https://example.com/t": (200, "NiceTool page")}))
        self.assertIsNone(why)
        blob = json.dumps(v)
        self.assertNotIn("\\u001b", blob); self.assertNotIn("\\u0007", blob); self.assertNotIn("\\u0000", blob)
        self.assertEqual(v["name"], "NiceTool"); self.assertEqual(v["install"], "npm i nice")


class Verify(unittest.TestCase):
    def check(self, item, table, have=HAVE):
        return discover.verify_item(item, have, getter(table))

    def test_a_real_github_repo_passes_with_real_metadata(self):
        v, why = self.check({"name": "good-tool", "kind": "mcp", "why": "better", "url": "https://github.com/acme/good-tool"}, {API + "acme/good-tool": (200, gh_json())})
        self.assertIsNone(why)
        self.assertEqual((v["stars"], v["kind"]), (1234, "mcp")); self.assertEqual(v["pushed"], (TODAY - dt.timedelta(days=30)).isoformat())

    def test_a_made_up_github_repo_is_dropped(self):
        v, why = self.check({"name": "screenshot-to-code", "url": "https://github.com/iankleinschmidt/screenshot-to-code"}, {})
        self.assertIsNone(v); self.assertIn("does not exist", why)   # the exact hallucination seen from the real model

    def test_archived_stale_and_mismatched_repos_are_dropped(self):
        url = "https://github.com/acme/good-tool"
        self.assertIn("archived", self.check({"name": "good-tool", "url": url}, {API + "acme/good-tool": (200, gh_json(archived=True))})[1])
        self.assertIn("no push for", self.check({"name": "good-tool", "url": url}, {API + "acme/good-tool": (200, gh_json(days_ago=900))})[1])
        self.assertIn("does not match", self.check({"name": "fancy-widget", "url": url}, {API + "acme/good-tool": (200, gh_json())})[1])

    def test_github_rate_limit_falls_back_to_the_page(self):
        table = {API + "acme/good-tool": (403, ""), "https://github.com/acme/good-tool": (200, "<h1>good-tool</h1>")}
        v, why = self.check({"name": "good-tool", "url": "https://github.com/acme/good-tool"}, table)
        self.assertIsNone(why); self.assertIsNone(v["stars"])

    def test_other_sites_need_a_reachable_page_that_mentions_the_name(self):
        u = "https://tools.example.com/thing"
        self.assertIsNone(self.check({"name": "ThingKit", "url": u}, {u: (200, "welcome to thingkit")})[1])
        self.assertIn("not mention", self.check({"name": "ThingKit", "url": u}, {u: (200, "totally unrelated")})[1])
        self.assertIn("not reachable", self.check({"name": "ThingKit", "url": u}, {u: (500, "")})[1])
        self.assertIn("not reachable", self.check({"name": "ThingKit", "url": u}, {})[1])

    def test_private_urls_are_never_fetched(self):
        calls = []
        def spy(url): calls.append(url); return 200, "x"
        for url in ("http://example.com/x", "https://127.0.0.1/x", "https://localhost/x", "https://192.168.0.2/x"):
            v, why = discover.verify_item({"name": "thing", "url": url}, HAVE, spy)
            self.assertIsNone(v); self.assertIn("no usable https url", why)
        self.assertEqual(calls, [])

    def test_things_you_already_have_are_dropped_and_lists_are_capped_and_deduped(self):
        self.assertIn("already have", discover.verify_item({"name": "Impeccable", "url": "https://example.com/i"}, HAVE, getter({}))[1])
        table = {f"https://example.com/{i}": (200, f"tool{i}") for i in range(6)}
        raw = [{"name": f"tool{i}", "url": f"https://example.com/{i}"} for i in range(6)] + [{"name": "tool0", "url": "https://example.com/0"}]
        ok, _ = discover.verify_all(raw, HAVE, getter(table))
        self.assertEqual(len(ok), 3)
        self.assertEqual(discover.verify_all("nonsense", HAVE, getter({})), ([], []))

    def test_topic_key_is_stable_for_the_same_kind_of_task(self):
        a = {"task": "ui-design", "summary": "Improve visual design of the shoe store website"}
        self.assertEqual(discover.topic_key(a), discover.topic_key(dict(a)))
        self.assertTrue(discover.topic_key(a).startswith("ui-design:"))


class Asking(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); s = self.tmp.name
        self.saved = (coach.STATE, coach.CONFIG); coach.STATE = os.path.join(s, "coach"); coach.CONFIG = s
        make_config(s)
        self.env = {k: os.environ.get(k) for k in ("COACHLINE_CLAUDE", "FAKE_LOG", "FAKE_JSON_WEB", "FAKE_MODE", "COACHLINE_FETCH_STUB")}
        os.environ["COACHLINE_CLAUDE"] = f'"{PY}" "{FAKE}"'; os.environ["FAKE_LOG"] = os.path.join(s, "sent.log"); os.environ.pop("FAKE_MODE", None)
        self.stub = os.path.join(s, "stub.json"); os.environ["COACHLINE_FETCH_STUB"] = self.stub
        with open(self.stub, "w") as f: json.dump({"https://tools.example.com/g": {"status": 200, "text": "GreatKit is here"}}, f)
        os.environ["FAKE_JSON_WEB"] = json.dumps({"items": [{"name": "GreatKit", "kind": "tool", "why": "does it better", "url": "https://tools.example.com/g", "install": "npm i greatkit"},
                                                            {"name": "Ghost", "kind": "tool", "why": "invented", "url": "https://tools.example.com/none"}]})
        self.adv = {"task": "ui-design", "summary": "improve visual design of a shoe store website", "use": []}

    def tearDown(self):
        coach.STATE, coach.CONFIG = self.saved; self.tmp.cleanup()
        for k, v in self.env.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

    def calls(self):
        return read(os.environ["FAKE_LOG"]).count("=====") if os.path.exists(os.environ["FAKE_LOG"]) else 0

    def test_only_discovery_gets_the_web_tools_and_only_verified_items_come_back(self):
        items = discover.for_advice(self.adv)
        self.assertEqual([i["name"] for i in items], ["GreatKit"])       # 'Ghost' 404s in verification
        log = read(os.environ["FAKE_LOG"])
        self.assertIn("--tools WebSearch,WebFetch --setting-sources  --allowedTools WebSearch,WebFetch", log.replace("  ", "  "))
        self.assertIn("ui-design: improve visual design of a shoe store website", log)   # the generic kind-of-task, nothing else
        self.assertNotIn("USER PROMPT", log)                                            # the user's own prompt is never part of a web search call
        import advisor
        os.environ["FAKE_JSON"] = "{}"; advisor.advise("landing page please", [])
        advise_args = [l for l in read(os.environ["FAKE_LOG"]).splitlines() if l.startswith("ARGS:")][-1]
        self.assertNotIn("WebSearch", advise_args)                       # the advisor itself never gets web access

    def test_results_are_cached_per_topic_and_fresh_forces_a_new_search(self):
        discover.for_advice(self.adv); discover.for_advice(self.adv)
        self.assertEqual(self.calls(), 1)
        discover.for_advice(self.adv, fresh=True)
        self.assertEqual(self.calls(), 2)
        with open(os.path.join(coach.STATE, "discover-cache.json")) as f: c = json.load(f)
        for v in c.values(): v["ts"] = time.time() - 2 * 86400
        with open(os.path.join(coach.STATE, "discover-cache.json"), "w") as f: json.dump(c, f)
        discover.for_advice(self.adv)
        self.assertEqual(self.calls(), 3)                                # expired after 24h

    def test_discovery_never_raises(self):
        os.environ["FAKE_MODE"] = "fail"
        self.assertEqual(discover.for_advice(self.adv), [])
        os.environ["FAKE_MODE"] = "bad"
        self.assertEqual(discover.for_advice(self.adv, fresh=True), [])

    def test_display_lines_label_web_finds_and_show_evidence(self):
        items = [{"name": "good-tool", "kind": "mcp", "why": "better", "url": "https://github.com/acme/good-tool", "install": "npm i good-tool", "stars": 1234, "pushed": "2026-08-01"}]
        text = "\n".join(t for _k, t in discover.lines(items, 80))
        for want in ("web-found, not installed", "better: good-tool (mcp) - better", "1.2k stars", "pushed 2026-08-01", "https://github.com/acme/good-tool", "install: npm i good-tool"):
            self.assertIn(want, text)
        self.assertIn("better: good-tool (mcp) 1.2k stars - better  https://github.com/acme/good-tool", discover.compact(items)[0])
        self.assertEqual(discover.lines([]), [])


class EndToEnd(unittest.TestCase):
    ADVICE = json.dumps({"task": "ui-design", "summary": "polishing a shoe store website", "use": [], "get": [], "tips": ["Name the style."],
                         "workflow": ["Sketch", "Build"], "after": "Polish the website."})
    WEB = json.dumps({"items": [{"name": "GreatKit", "kind": "tool", "why": "does it \x1b[31mbetter", "url": "https://tools.example.com/g", "install": "npm i greatkit"},
                                {"name": "Ghost", "kind": "tool", "why": "invented", "url": "https://tools.example.com/none"}]})

    def wait(self, path, want, seconds=30):
        end = time.time() + seconds
        while time.time() < end:
            if os.path.exists(path) and want in read(path): return
            time.sleep(0.2)
        self.fail(f"{want!r} never appeared in {path}")

    def test_background_job_adds_verified_discoveries_to_statusline_and_panel(self):
        with tempfile.TemporaryDirectory() as cfg:
            write_history(cfg, ["make my shoe store website look modern and polished for every customer please"])
            stub = os.path.join(cfg, "stub.json")
            with open(stub, "w") as f: json.dump({"https://tools.example.com/g": {"status": 200, "text": "GreatKit"}}, f)
            env = dict(FAKE_JSON=self.ADVICE, FAKE_JSON_WEB=self.WEB, COACHLINE_FETCH_STUB=stub)
            self.assertEqual(run(cfg, "setup.py").returncode, 0)
            self.assertEqual(run(cfg, "setup.py", "--advisor", "on").returncode, 0)
            self.assertEqual(run(cfg, "setup.py", "--discover", "on").returncode, 0)
            self.assertTrue(json.loads(read(os.path.join(cfg, "coach", "config.json")))["discover"])
            run(cfg, "statusline.py", **env)                                   # starts the detached job
            log = os.path.join(cfg, "coach", "rewrites.jsonl")
            self.wait(log, "discovery")
            recs = [json.loads(l) for l in read(log).splitlines()]
            self.assertEqual(len(recs), 2)                                     # advice first, then advice + discovery, same key
            self.assertEqual(recs[0]["key"], recs[1]["key"]); self.assertNotIn("discovery", recs[0])
            self.assertEqual([d["name"] for d in recs[1]["discovery"]], ["GreatKit"])
            shown = run(cfg, "statusline.py", **env).stdout
            self.assertIn("better: GreatKit (tool)", shown)
            self.assertNotIn("\x1b[31mbetter", shown)                          # model/web text is cleaned; our own colours remain
            panel = run(cfg, "watch.py", "--once", "--width", "150", "--height", "40").stdout
            flat = " ".join(panel.replace("│", "").split())
            self.assertIn("web-found, not installed", flat); self.assertIn("better: GreatKit (tool)", flat)
            self.assertIn("install: npm i greatkit", flat)

    def test_discovery_stays_off_unless_enabled(self):
        with tempfile.TemporaryDirectory() as cfg:
            write_history(cfg, ["make my shoe store website look modern and polished for every customer please"])
            run(cfg, "setup.py"); run(cfg, "setup.py", "--advisor", "on")
            env = dict(FAKE_JSON=self.ADVICE, FAKE_JSON_WEB=self.WEB)
            run(cfg, "statusline.py", **env)
            self.wait(os.path.join(cfg, "coach", "rewrites.jsonl"), "advice")
            time.sleep(1)
            self.assertNotIn("WebSearch", read(os.path.join(cfg, "sent.log")))  # no web call was ever made


if __name__ == "__main__":
    unittest.main()
