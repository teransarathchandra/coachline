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
        self.assertEqual((v["stars"], v["kind"]), (1234, "tool")); self.assertEqual(v["pushed"], (TODAY - dt.timedelta(days=30)).isoformat())

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
        self.assertEqual(len(ok), 4)
        self.assertEqual(discover.verify_all("nonsense", HAVE, getter({})), ([], []))

    def test_old_kinds_are_tools_and_install_is_kept_for_tools_only(self):
        u = "https://example.com/d"
        v, _ = self.check({"name": "Thing", "kind": "mcp", "url": u, "install": "npx thing"}, {u: (200, "thing")})
        self.assertEqual((v["kind"], v["install"]), ("tool", "npx thing"))
        v, _ = self.check({"name": "WCAG", "kind": "docs", "url": u, "install": "npm i x"}, {u: (200, "wcag 2.2")})
        self.assertEqual((v["kind"], v["install"]), ("docs", ""))
        v, _ = self.check({"name": "Linear", "kind": "inspo", "url": u}, {u: (200, "linear")})
        self.assertEqual(v["kind"], "inspo")

    def test_items_for_an_older_major_than_the_stack_are_dropped(self):
        stack = ["node", "next@15", "react@19", "go@1.22"]
        self.assertTrue(discover.older_major({"name": "Next.js 13 app router guide", "why": ""}, stack))
        self.assertTrue(discover.older_major({"name": "Upgrade kit", "why": "made for nextjs 14"}, stack))
        self.assertFalse(discover.older_major({"name": "Next.js 15 caching", "why": "for the app router"}, stack))
        self.assertFalse(discover.older_major({"name": "Next 15 codemods for apps on Next 14", "why": ""}, stack))   # names the current major too
        self.assertFalse(discover.older_major({"name": "Playwright", "why": "e2e tests in context 3"}, stack))
        u = "https://example.com/n"
        v, why = discover.verify_item({"name": "Next 13 guide", "kind": "docs", "url": u}, HAVE, getter({u: (200, "next 13 guide")}), stack=stack)
        self.assertIsNone(v); self.assertIn("older version", why)

    def test_topic_key_includes_the_stack(self):
        a = {"task": "frontend", "topic": "checkout page ui", "summary": "whatever"}
        self.assertNotEqual(discover.topic_key(a, ["next@15"]), discover.topic_key(a, ["vue@3"]))
        self.assertEqual(discover.topic_key(a, ["react@19", "next@15"]), discover.topic_key(a, ["next@15", "react@19"]))

    def test_pause_until_reads_the_reset_time_or_waits_an_hour(self):
        now = dt.datetime(2026, 10, 2, 10, 0).timestamp()
        self.assertEqual(discover.pause_until("Claude AI usage limit reached|1795000000", now), 1795000000)
        at = lambda s: dt.datetime.fromtimestamp(discover.pause_until(s, now)).strftime("%d %H:%M")
        self.assertEqual(at("5-hour limit reached \u2219 resets 2pm"), "02 14:00")
        self.assertEqual(at("usage limit reached, resets at 9:30"), "03 09:30")          # already past today: tomorrow
        self.assertEqual(discover.pause_until("usage limit reached", now), now + 3600)    # a format we have never seen

    def test_topic_key_is_stable_for_the_same_kind_of_task(self):
        a = {"task": "ui-design", "summary": "Improve visual design of the shoe store website"}
        self.assertEqual(discover.topic_key(a), discover.topic_key(dict(a)))
        self.assertTrue(discover.topic_key(a).startswith("ui-design:"))


class Asking(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); s = self.tmp.name
        self.saved = (coach.STATE, coach.CONFIG, coach.USER_CFG); coach.STATE = os.path.join(s, "coach"); coach.CONFIG = s
        coach.USER_CFG = os.path.join(s, "coach", "config.json")
        make_config(s)
        self.env = {k: os.environ.get(k) for k in ("COACHLINE_CLAUDE", "FAKE_LOG", "FAKE_JSON_WEB", "FAKE_MODE", "FAKE_ERR", "COACHLINE_FETCH_STUB")}
        os.environ["COACHLINE_CLAUDE"] = f'"{PY}" "{FAKE}"'; os.environ["FAKE_LOG"] = os.path.join(s, "sent.log"); os.environ.pop("FAKE_MODE", None)
        self.stub = os.path.join(s, "stub.json"); os.environ["COACHLINE_FETCH_STUB"] = self.stub
        with open(self.stub, "w") as f: json.dump({"https://tools.example.com/g": {"status": 200, "text": "GreatKit is here"}}, f)
        os.environ["FAKE_JSON_WEB"] = json.dumps({"items": [{"name": "GreatKit", "kind": "tool", "why": "does it better", "url": "https://tools.example.com/g", "install": "npm i greatkit"},
                                                            {"name": "Ghost", "kind": "tool", "why": "invented", "url": "https://tools.example.com/none"}]})
        self.adv = {"task": "ui-design", "summary": "improve visual design of a shoe store website", "topic": "shoe store ui", "use": []}

    def tearDown(self):
        coach.STATE, coach.CONFIG, coach.USER_CFG = self.saved; self.tmp.cleanup()
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
        self.assertIn('"ui-design: shoe store ui"', log)                                 # the generic topic, nothing else of the prompt
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
        for v in c.values(): v["ts"] = time.time() - 8 * 86400
        with open(os.path.join(coach.STATE, "discover-cache.json"), "w") as f: json.dump(c, f)
        discover.for_advice(self.adv)
        self.assertEqual(self.calls(), 3)                                # expired after 7 days

    def test_research_gets_topic_stack_and_installed_names_on_the_research_model(self):
        discover.for_advice(self.adv, ["node", "next@15"])
        log = read(os.environ["FAKE_LOG"])
        for want in ("next@15", "design-polish", "--model sonnet"): self.assertIn(want, log)
        self.assertNotIn("USER PROMPT", log)

    def test_a_usage_limit_pauses_research_and_fresh_ignores_the_pause(self):
        os.environ["FAKE_MODE"] = "fail"; os.environ["FAKE_ERR"] = "Claude AI usage limit reached, resets 11pm"
        self.assertEqual(discover.for_advice(self.adv), [])
        self.assertIsNotNone(discover.paused_until())
        self.assertEqual(discover.for_advice({**self.adv, "topic": "something else"}), [])
        self.assertEqual(self.calls(), 1)                                                   # paused: no second call
        os.environ.pop("FAKE_MODE")
        self.assertEqual([i["name"] for i in discover.for_advice(self.adv, fresh=True)], ["GreatKit"])   # asked for by hand
        self.assertEqual(self.calls(), 2)

    def test_an_ordinary_failure_does_not_pause(self):
        os.environ["FAKE_MODE"] = "fail"
        discover.for_advice(self.adv)
        self.assertIsNone(discover.paused_until())

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

    TEXT = "make my shoe store website look modern and polished for every customer please"

    def job(self, cfg, **env):
        """What the panel starts for a prompt: `coach.py --bg-rewrite --key K`, run synchronously here."""
        key = coach.prompt_key((1750000000.0, "proj", self.TEXT))
        return run(cfg, "coach.py", "--bg-rewrite", "--key", key, **env)

    def test_the_analysis_job_adds_verified_discoveries_that_the_panel_shows(self):
        with tempfile.TemporaryDirectory() as cfg:
            write_history(cfg, [self.TEXT])
            stub = os.path.join(cfg, "stub.json")
            with open(stub, "w") as f: json.dump({"https://tools.example.com/g": {"status": 200, "text": "GreatKit"}}, f)
            self.assertEqual(run(cfg, "setup.py", "--discover", "on").returncode, 0)
            self.assertTrue(json.loads(read(os.path.join(cfg, "coach", "config.json")))["research"])
            r = self.job(cfg, FAKE_JSON=self.ADVICE, FAKE_JSON_WEB=self.WEB, COACHLINE_FETCH_STUB=stub)
            self.assertEqual(r.returncode, 0, r.stderr)
            recs = [json.loads(l) for l in read(os.path.join(cfg, "coach", "rewrites.jsonl")).splitlines()]
            self.assertEqual(len(recs), 2)                                     # advice first, then advice + discovery, same key
            self.assertEqual(recs[0]["key"], recs[1]["key"]); self.assertNotIn("discovery", recs[0])
            self.assertEqual([d["name"] for d in recs[1]["discovery"]], ["GreatKit"])      # 'Ghost' 404s in verification
            panel = run(cfg, "watch.py", "--once", "--width", "150", "--height", "40").stdout
            flat = " ".join(panel.split())
            self.assertIn("found on the web, not installed", flat); self.assertIn("better: GreatKit (tool)", flat)
            self.assertIn("install: npm i greatkit", flat)
            self.assertNotIn("\x1b[31m", panel)                                 # model/web text is cleaned of escape codes

    def test_research_off_means_no_web_call(self):
        with tempfile.TemporaryDirectory() as cfg:
            write_history(cfg, [self.TEXT])
            self.assertEqual(run(cfg, "setup.py", "--research", "off").returncode, 0)
            self.assertEqual(self.job(cfg, FAKE_JSON=self.ADVICE, FAKE_JSON_WEB=self.WEB).returncode, 0)
            self.assertEqual(len(read(os.path.join(cfg, "coach", "rewrites.jsonl")).splitlines()), 1)   # advice only
            self.assertNotIn("WebSearch", read(os.path.join(cfg, "sent.log")))


if __name__ == "__main__":
    unittest.main()
