"""Stand-in clipboard command for tests: writes stdin to the file named by CLIP_OUT."""
import os, sys
with open(os.environ["CLIP_OUT"], "wb") as f: f.write(sys.stdin.buffer.read())
