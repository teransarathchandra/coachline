"""The README's GIFs that need no Claude session, captured from the website so the two always match: it serves site/ (with
docs/assets copied in, as the Pages workflow does), then
- plays each illustration scene and screenshots it frame by frame;
- shows the real panel's frames (site_frames.py --sequences) one after another in the site's terminal frame.
  python3 docs/demo/scene_gifs.py            all of them
  python3 docs/demo/scene_gifs.py hint use   only those (hint hold use newtask browse patterns library)
Needs Playwright with Chromium and ffmpeg. Writes docs/assets/<name>.gif.
"""
import functools, http.server, json, os, shutil, subprocess, sys, tempfile, threading
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FPS, WIDTH = 12, 720
# README name: (scene, seconds to capture; a little past the scene's own script, so the GIF loops on a settled frame)
SCENES = {"hint": ("hint", 11.5), "hold": ("hold", 7.8), "use": ("use", 10.6), "newtask": ("research", 9.4)}
PANEL = ("browse", "patterns", "library")                                     # real panel frames, each held HOLD seconds
HOLD = 1.8


def panel_gif(pg, name, frames, tmp):
    """The Library section's terminal frame shows each of the panel's frames in turn; one screenshot each, held HOLD seconds."""
    term = pg.locator("#k-l pre.term.wide-only"); target = term.locator("xpath=ancestor::div[contains(@class,'chrome')][1]")
    target.scroll_into_view_if_needed(); d = os.path.join(tmp, name); os.makedirs(d)
    listing = os.path.join(d, "frames.txt")
    with open(listing, "w") as f:
        for i, body in enumerate(frames):
            term.evaluate("(el, body) => el.innerHTML = body", body)
            png = os.path.join(d, f"{i:02d}.png"); target.screenshot(path=png)
            f.write(f"file '{png}'\nduration {HOLD}\n")
        f.write(f"file '{png}'\n")                                                 # the concat demuxer drops the last duration otherwise
    out = os.path.join(ROOT, "docs", "assets", f"{name}.gif")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing,
                    "-vf", f"scale={WIDTH}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=none",
                    "-fps_mode", "vfr", "-loop", "0", out], check=True)                # one GIF frame per panel frame, each with its own delay
    print(f"ok   docs/assets/{name}.gif ({os.path.getsize(out) // 1024} KB)")


def main(names):
    tmp = tempfile.mkdtemp(); site = os.path.join(tmp, "site")
    shutil.copytree(os.path.join(ROOT, "site"), site); shutil.copytree(os.path.join(ROOT, "docs", "assets"), os.path.join(site, "assets"))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=site); handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        b = p.chromium.launch()
        sequences = {}
        if any(n in PANEL for n in names):
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            sequences = json.loads(subprocess.run([sys.executable, os.path.join(ROOT, "docs", "demo", "site_frames.py"), "--sequences"],
                                                  env=env, capture_output=True, text=True, encoding="utf-8", check=True).stdout)
        for name in names:
            if name in PANEL:
                pg = b.new_page(viewport={"width": WIDTH + 80, "height": 1000}, device_scale_factor=1, color_scheme="dark")
                pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/"); pg.wait_for_timeout(800)
                panel_gif(pg, name, sequences[name], tmp); continue
            scene, seconds = SCENES[name]
            pg = b.new_page(viewport={"width": WIDTH + 80, "height": 900}, device_scale_factor=1, color_scheme="dark")
            pg.clock.install()                                                     # page time moves only when told: one frame, 1/FPS s
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/"); pg.clock.run_for(800)
            box = pg.locator(f'.scene[data-scene="{scene}"]')
            pg.evaluate(f"""(() => {{ const b = document.querySelector('.scene[data-scene="{scene}"]'); const panel = b.closest('.tabpanel');
                if (panel) panel.hidden = false; }})()""")
            target = box.locator("xpath=ancestor::div[contains(@class,'chrome')][1]")
            target.scroll_into_view_if_needed(); pg.clock.run_for(1500)
            frames = os.path.join(tmp, name); os.makedirs(frames)
            box.dispatch_event("scene:play")
            for i in range(int(seconds * FPS)):
                target.screenshot(path=os.path.join(frames, f"{i:04d}.png"), animations="disabled"); pg.clock.run_for(1000 // FPS)
            out = os.path.join(ROOT, "docs", "assets", f"{name}.gif")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(frames, "%04d.png"),
                            "-vf", f"scale={WIDTH}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=none",
                            "-loop", "0", out], check=True)
            print(f"ok   docs/assets/{name}.gif ({os.path.getsize(out) // 1024} KB)")
        b.close()
    srv.shutdown(); shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    known = [*SCENES, *PANEL]
    bad = [n for n in sys.argv[1:] if n not in known]
    if bad: sys.exit(f"unknown GIF {bad[0]}; one of: {', '.join(known)}")
    main(sys.argv[1:] or known)
