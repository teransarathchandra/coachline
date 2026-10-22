# Handoff: record coachline's GIFs and screenshots on the Mac

Paste this whole file into a fresh Claude Code window on the Mac, opened in the coachline repo. It is self-contained.

## Context

- **Repo:** coachline, a Claude Code plugin (github.com/teransarathchandra/coachline). Releases 0.18 to 0.21.1 added features the current GIFs don't show:
  - the quality meter and motion in the panel
  - **Use**, which fills the prompt box
  - the hint under the prompt box as you type
  - the outcome evidence line
  - opt-in hold
  - the Library, in the pane and in the standalone panel (`l`)
- **Website:** 0.22 (PR "feat: the coachline website and brand refresh") published https://teransarathchandra.github.io/coachline/ with the old GIFs. Your job is to swap in new recordings made on this Mac.
- **Where things live:**
  - all recording material is in `docs/demo/`
  - outputs go to `docs/assets/`
  - the website copies `docs/assets/` at deploy time, so new GIFs reach the site and the README together

## Rules (from the owner's CLAUDE.md)

- **Git hygiene:**
  - Never add Co-Authored-By, "Generated with Claude", or any Claude trace to commits or PRs.
  - Don't commit or push unless the owner asks. Stage only the files of this task, never `git add -A` or `.`.
- **Messages:**
  - Commit message: one line, conventional, matching `git log -n 15 --oneline` (this repo has no ticket keys).
  - PR: a title, plus a description of ONE short plain-English sentence.
- **Merging:** don't merge to `main`. Show the merge command and its rollback, then wait for the owner.
- **Installing tools:** read its README first, report its dependencies, and wait for the owner's OK.
- **No real data in a recording:** the tapes use a separate demo login and made-up chats.

## Steps

1. **Sync.** Run `git switch main && git pull`, then `git switch -c docs/mac-recordings`.
2. **Check the tools** (report anything missing before installing; see Rules):
   - `vhs --version` (brew install vhs; it brings ttyd)
   - `ffmpeg -version`
   - `python3 -c "import PIL"` (pip3 install pillow)
   - `claude --version`, which must be **2.1.287 or newer** for the pane; ideally the newest
3. **Demo login, once:** ask the owner to run `CLAUDE_CONFIG_DIR=~/.claude-coachline-demo claude auth login`. It's interactive, so you can't do it yourself. It's a separate config, so none of the owner's history or plugins appear in the recordings.
4. **Check the tests first:**
   - `python3 -W error::ResourceWarning -m unittest discover -s tests` must be OK.
   - `claude plugin test .` must pass.
5. **Do a test take of each new tape and look at it before recording everything.** Open each GIF or mp4 and check it frame by frame.
   - `bash docs/demo/record-all.sh library`
     - Fake Claude, fully deterministic.
     - Expect: `l` opens the Library with 3 saved prompts, `j j` moves to the third, `c` shows "copied the saved prompt", and `l` goes back.
   - `bash docs/demo/record-all.sh install hint`
     - Real Claude. `install` comes first: it reinstalls the plugin in the demo login.
     - Expect: after "fix it now please" and a pause, the line under the prompt box ends with `· ▰▱▱▱▱  name a file, function, error or number` (or the beginner wording, with "— so Claude doesn't have to guess"). The meter fills as the file and the done-when are typed.
     - If no tail appears: run `claude --debug` in the demo config and look for `coachline:` lines. The hint needs Python on PATH. Note what you see.
   - `bash docs/demo/record-all.sh use`
     - Real Claude. This one is the least certain: `use.tape` presses the pane's **Use** button with `Ctrl+X`, `Tab`, `Enter`, which may land on a different control.
     - Find the key sequence that focuses **Use** in the pane: try it by hand in the demo config first. Then fix the `Ctrl+X` / `Tab` lines in `use.tape` and the `timeline` / `camera` in `use.zoom.json`. The timeline is in recording seconds; the camera keyframes are in GIF seconds, as `[t, zoom, cx, cy]`; see the docstring of `docs/demo/zoom.py`.
     - Expect: the prompt box fills with the enhanced prompt, `[ASK: …]` parts in bold, and the message "in your prompt box: fill the [ASK] parts, then send". Nothing is sent.
6. **Record everything:** `bash docs/demo/record-all.sh`, about 6–8 minutes. Then check every GIF by eye:
   - no real names, paths or history appear
   - the panel's name chip is coral
   - nothing overlaps or is cut off
   - text is readable at the README's width
7. **Stills, taken by hand in light and dark themes, with nothing personal on screen:**
   - `docs/assets/desktop.png`: the Claude desktop app with the coachline pane, light and dark side by side, about 1200×1380, the same layout as the current file
   - `docs/assets/editor.png`: VS Code with the Claude Code extension and the coachline pane, light and dark, the same layout as the current file
   - `docs/assets/screenshot.png` comes from the `still` in `website.zoom.json`; `record-all.sh website` rewrites it
8. **Wire the new GIFs into the README and the website:**
   - **README.md:** under "### 4 · Keep what works", add `hint.gif` after the hint bullet, `use.gif` after the Use bullet, and `library.gif` after the Library bullet. Use `<img src="docs/assets/<name>.gif" alt="<what it shows, one sentence>" width="100%">` with a real alt text.
   - **site/index.html:** in the "How it works" `.steps`, add a step 04 "Keep what works", with `assets/use.gif` and a one-line description. Then check the page at 390 px and 1280 px wide, in light and dark (a local server: `cd _site && python3 -m http.server`, after copying as `.github/workflows/pages.yml` does): no horizontal scroll, no overlaps, no broken images.
9. **Social preview:** `python3 docs/demo/social.py` writes `docs/assets/social.png` (needs Playwright). Then ask the owner to upload it in GitHub: Settings → General → Social preview. That step has no API.
10. **Live check of 0.19–0.21 in the demo login** (the owner hasn't seen these in a real session yet). Report what works and what doesn't, with `claude --debug` lines for anything broken:
    - the hint under the box after a pause
    - **Use** on an analysed prompt
    - `/coach hold on`, then a vague prompt is held, and Enter again sends it
    - a prompt that works first time appears in the Library after two clean follow-ups, and a similar draft then gets `↻ similar prompt worked before`
    - `l` in the standalone panel (`/coach watch`)
11. **Commit, when the owner asks:**
    - Stage only `docs/assets/*.gif docs/assets/*.png docs/demo/*.tape docs/demo/*.zoom.json README.md site/index.html`.
    - Message: `docs: GIFs and screenshots recorded on macOS for 0.18–0.21`.
    - Push, then open a PR: title as the message, one-sentence description.
    - Don't merge; the owner merges. The pages workflow redeploys the site once it is merged.

## Done when

- **New GIFs:** `docs/assets/{install,prompt,website,browse,patterns,hint,use,library}.gif` are re-recorded on the Mac and checked by eye.
- **Stills:** `desktop.png`, `editor.png` and `screenshot.png` are fresh, light and dark.
- **Wired in:** the README and the website show the hint, Use and Library GIFs, and the site passes the 390 / 1280, light / dark check.
- **Tests still pass:** the unittest suite and `claude plugin test .`.
- **Reported:** the step 10 live checks, with anything broken written up.
- **Open PR, not merged:** the PR is open, with no Claude trace, waiting for the owner.

## Don't touch

- `scripts/`, `hooks/` and `tests/`, unless step 10 finds a bug. Then describe it and ask before fixing.
- `.github/workflows/`, `CHANGELOG.md` and the version in `.claude-plugin/plugin.json`.
- The owner's own `~/.claude`. Recordings use `~/.claude-coachline-demo` only, and `real.sh` refuses to reset `~/.claude`.
