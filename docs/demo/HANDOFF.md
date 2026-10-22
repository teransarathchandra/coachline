# coachline's demo media: what is recorded, what is generated

Paste this file into a fresh Claude Code window in the coachline repo when the media needs redoing. Outputs go to `docs/assets/`;
the website copies that folder at deploy time, so the README and the site change together.

## What makes each file

| Files | Made by | Needs |
| --- | --- | --- |
| `install.gif`, `prompt.gif`, `screenshot.png` (from the `website` take's still) | `bash docs/demo/record-all.sh` on a Mac: the real Claude Code | vhs, ffmpeg, Pillow, the demo login |
| `desktop.png`, `editor.png` | taken by hand: the Claude desktop app and VS Code with the pane, light and dark side by side | clean windows, nothing personal on screen |
| `hint.gif`, `use.gif`, `hold.gif`, `newtask.gif` | `python3 docs/demo/scene_gifs.py`: the website's illustrations, played and captured | Playwright with Chromium, ffmpeg |
| `browse.gif`, `patterns.gif`, `library.gif` | `python3 docs/demo/scene_gifs.py`: the standalone panel's real frames (`site_frames.py --sequences`) | the same |
| the site's MP4s and WebPs | `bash docs/demo/web_media.sh`, after any recording | ffmpeg, a WebP encoder |
| the site's panel frames | `python3 docs/demo/site_frames.py`, after a change to the panel | nothing |

Change an illustration in `site/index.html` (its markup and its script in `SCRIPTS`), then rerun `scene_gifs.py` so the README matches.
The illustrations use coachline's real messages: check a changed hint with `coach.hint_for(text)` and `watch.meter(text)`.

## Recording on the Mac

1. `vhs --version`, `ffmpeg -version`, `python3 -c "import PIL"`, and `claude --version` (2.1.287 or newer).
2. The demo login, once, run by the owner (it is interactive): `CLAUDE_CONFIG_DIR=~/.claude-coachline-demo claude auth login`.
   It is a separate config, so none of the owner's history or plugins appear.
3. `bash docs/demo/record-all.sh` (or `install`, `prompt`, `website` alone), then check each GIF by eye: no real names, paths or
   history; nothing cut off; readable at the README's width.
4. `bash docs/demo/web_media.sh`. Re-crop `docs/assets/screenshot-pane.png` (the pane alone, for phones) if the pane moved.

## Rules (from the owner's CLAUDE.md)

- No Co-Authored-By, "Generated with Claude" or any Claude trace in commits or PRs.
- Commit or push only when the owner asks; stage only this task's files, never `git add -A` or `.`.
- One-line conventional commit message matching `git log -n 15 --oneline`; PR description one plain sentence.
- Don't merge; the owner merges in the browser.
- Before installing a tool: read its README, report its dependencies, and wait for the owner's OK.
- Don't touch `scripts/`, `hooks/`, `tests/`, `.github/workflows/`, or the owner's own `~/.claude`.
