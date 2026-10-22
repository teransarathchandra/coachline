"""Renders real frames of the standalone panel (scripts/watch.py, with seed.py's made-up chats) into site/index.html, between
<!-- frame:NAME --> and <!-- /frame --> markers, as HTML with the panel's colours as classes. Run from the repo root after a UI change:
  python3 docs/demo/site_frames.py
No real data: a throwaway config, the demo chats, a stand-in for `claude -p`.
"""
import html, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SITE = os.path.join(ROOT, "site", "index.html")
W, H = 74, 30
NARROW = 44                                                        # the same frames for phones, below 640px

if os.environ.get("SITE_FRAMES_CHILD") != "1":                    # coach.py fixes its paths at import: run in a fresh config
    cfg = tempfile.mkdtemp()
    env = {**os.environ, "CLAUDE_CONFIG_DIR": cfg, "SITE_FRAMES_CHILD": "1", "PYTHONIOENCODING": "utf-8",
           "COACHLINE_CLAUDE": f'"{sys.executable}" "{os.path.join(ROOT, "docs", "demo", "fake_claude.py")}"'}
    subprocess.run([sys.executable, os.path.join(ROOT, "docs", "demo", "seed.py")], env=env, check=True)
    sys.exit(subprocess.run([sys.executable, os.path.abspath(__file__)], env=env).returncode)

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coach, watch  # noqa: E402
watch.CODE.update(watch.TRUECOLOR)                                 # the coral of a 24-bit terminal, as on macOS

CLASS = {"1": "b", "7": "rev", "33": "y", "37": "w", "90": "dim", "91": "red", "92": "grn", "93": "ylw", "94": "blu", "95": "mag", "96": "cyn",
         "97": "wht", "41": "bg-red", "44": "bg-blu", "100": "bg-bar", "104": "bg-blu2"}


def to_html(line):
    """ANSI SGR to spans: the 16 colours as classes (the page's terminal palette), 24-bit colours inline."""
    out, cls, style = [], [], {}
    for tok in re.split(r"(\x1b\[[0-9;]*m)", line):
        m = re.fullmatch(r"\x1b\[([0-9;]*)m", tok)
        if not m:
            if tok:
                attrs = ((f' class="{" ".join(dict.fromkeys(cls))}"' if cls else "")
                         + (f' style="{";".join(f"{k}:{v}" for k, v in style.items())}"' if style else ""))
                out.append(f"<span{attrs}>{html.escape(tok)}</span>" if attrs else html.escape(tok))
            continue
        c = [x for x in m.group(1).split(";") if x] or ["0"]; i = 0
        while i < len(c):
            if c[i] == "0": cls, style = [], {}
            elif c[i] in ("38", "48") and c[i + 1:i + 2] == ["2"]:
                style["color" if c[i] == "38" else "background"] = "#%02x%02x%02x" % tuple(int(x) for x in c[i + 2:i + 5]); i += 4
            elif c[i] in CLASS: cls.append(CLASS[c[i]])
            i += 1
    return "".join(out)


class IO:
    def copy(self, text): return "pbcopy"
    def enhance(self, key): pass
    def used_saved(self, i): return True
    def forget_saved(self, i): return True


def frame(keys=(), sel=None, w=W):
    st = watch.build(coach.HIST); ui = watch.new_ui()
    if sel is not None: ui["sel"] = sel
    for k in keys: watch.handle(ui, st, k, IO())
    return "\n".join(to_html(r) for r in watch.render(st, ui, w, H, color=True))


frames = {
    "analyse": frame(sel=1),                                       # Claude's analysis of a vague prompt: Improve and the enhanced prompt
    "copy": frame(["c"]),                                          # the newest prompt's card, Copied just pressed
    "library": frame(["l", "j"]),                                  # the Library, the second saved prompt chosen
    "analyse-narrow": frame(sel=1, w=NARROW),
    "copy-narrow": frame(["c"], w=NARROW),
    "library-narrow": frame(["l", "j"], w=NARROW),
}
page = open(SITE, encoding="utf-8").read()
for name, body in frames.items():
    page, n = re.subn(rf"(<!-- frame:{name} -->).*?(<!-- /frame -->)", lambda m: m.group(1) + body + m.group(2), page, flags=re.S)
    if n != 1: sys.exit(f"site/index.html has no single frame:{name} marker")
open(SITE, "w", encoding="utf-8", newline="\n").write(page)
print("frames:", ", ".join(frames))
