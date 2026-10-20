"""Turns a recording made at twice the GIF's size into the GIF, with the camera easing in on part of the screen and the waits cut.

    python3 docs/demo/zoom.py docs/demo/prompt.zoom.json

The plan (JSON) names the recording, the GIF, its timeline and the camera's keyframes. The timeline is a list of parts of the
recording, in its seconds: [a, b] plays a to b, [t, t, d] holds the frame at t for d seconds. The camera's keyframes are in the
GIF's seconds: [t, zoom, cx, cy] puts the view's centre at (cx, cy), as fractions of the frame, zoom times closer than the whole
frame. Between two keyframes the camera eases; before the first and after the last it holds. A recording at twice the GIF's size
keeps the text sharp up to zoom 2. "fps" sets the GIF's frame rate, "colors" its palette size. "still": [t, path] also saves the recording's frame at t as a PNG. Needs ffmpeg and Pillow
(pip install pillow); only for making the README's GIFs.
"""
import json, os, subprocess, sys, tempfile

from PIL import Image, ImageChops, ImageFilter

NOISE = 16                                              # a pixel that changes less than this between frames is the mp4's noise


def ease(x):
    return x * x * (3 - 2 * x)                          # smoothstep: starts and ends at rest


def camera(keys, t):
    """(zoom, cx, cy) at time t."""
    if t <= keys[0][0]: return keys[0][1:]
    for (t0, *a), (t1, *b) in zip(keys, keys[1:]):
        if t <= t1:
            k = ease((t - t0) / (t1 - t0)) if t1 > t0 else 1
            return [x + (y - x) * k for x, y in zip(a, b)]
    return keys[-1][1:]


def box(W, H, zoom, cx, cy):
    """The part of a W x H frame the camera sees, kept inside the frame."""
    w, h = W / zoom, H / zoom
    x = min(max(cx * W - w / 2, 0), W - w)
    y = min(max(cy * H - h / 2, 0), H - h)
    return (x, y, x + w, y + h)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return s["width"], s["height"], int(num) / int(den)


def main(plan_path):
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(plan_path, encoding="utf-8") as f: plan = json.load(f)
    src, dst = os.path.join(root, plan["input"]), os.path.join(root, plan["output"])
    W, H, fps = probe(src)
    ow, oh = plan.get("size", [W // 2, H // 2])
    timeline = plan.get("timeline") or [[0, 10 ** 6]]
    keys = plan.get("camera") or [[0, 1, 0.5, 0.5]]
    still = plan.get("still")
    want = []                                           # the recording's frame number for each frame of the GIF, in order
    for part in timeline:
        a, b = round(part[0] * fps), round(part[1] * fps)
        want += [a] * round(part[2] * fps) if len(part) > 2 else list(range(a, b))
    ofps = plan.get("fps", fps)                         # the GIF's frame rate: fewer frames, a smaller GIF
    want = [want[round(j * fps / ofps)] for j in range(int(len(want) * ofps / fps))]
    dec = subprocess.Popen(["ffmpeg", "-v", "quiet", "-i", src, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    with tempfile.TemporaryDirectory() as tmp:
        mid = os.path.join(tmp, "zoomed.mkv")
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ow}x{oh}", "-r", str(ofps),
                                "-i", "-", "-c:v", "ffv1", mid], stdin=subprocess.PIPE)
        size, n, img, prev, last, out = W * H * 3, -1, None, None, None, 0
        for idx in want:
            while n < idx:
                raw = dec.stdout.read(size)
                if len(raw) < size: break
                n += 1; img = None
                if still and n == round(still[0] * fps):
                    Image.frombytes("RGB", (W, H), raw).save(os.path.join(root, still[1]), optimize=True)
            if n < idx: break                           # the recording is shorter than the timeline
            if img is None: img = Image.frombytes("RGB", (W, H), raw)
            view = box(W, H, *camera(keys, out / ofps))
            frame = img.resize((ow, oh), Image.LANCZOS, box=view)
            if prev is not None and view == last:       # a still camera: keep the last frame's pixel where only the mp4's noise changed it
                moved = ImageChops.difference(frame, prev).convert("L").point(lambda v: 255 if v > NOISE else 0)
                moved = moved.filter(ImageFilter.MaxFilter(9))    # around a change, all of it: no faint outline of the old text left
                frame = Image.composite(frame, prev, moved)
            enc.stdin.write(frame.tobytes())
            prev, last, out = frame, view, out + 1
        dec.kill(); dec.stdout.close()
        enc.stdin.close(); enc.wait(); dec.wait()
        # one palette for the whole GIF; no dithering, which would speckle the terminal's flat colours
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mid, "-vf",
                        f"split[a][b];[a]palettegen=max_colors={plan.get('colors', 256)}:stats_mode=full[p];[b][p]paletteuse=dither=none:diff_mode=rectangle",
                        "-loop", "0", dst], check=True)
    print(f"{dst}: {os.path.getsize(dst) // 1024} KB")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
