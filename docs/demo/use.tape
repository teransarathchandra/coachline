# Records the Use GIF with the real Claude Code and the real coachline (installed by install.tape), at twice the GIF's size: a vague
# prompt is analysed, then Use puts the enhanced prompt in the prompt box with its [ASK] gaps in bold. Nothing is sent by Use.
# Run from the repo root after install.tape, then: vhs docs/demo/use.tape && python3 docs/demo/zoom.py docs/demo/use.zoom.json
# The pane's Use is a Button: in the terminal, ctrl+x tab focuses the pane's controls and Enter presses the focused one. Check the
# key sequence below on the first take (see docs/demo/HANDOFF.md, step 5) and adjust the Tab count to land on Use.
Output docs/demo/.rec/use.mp4
Source docs/demo/common.tape
Source docs/demo/hires.tape

Hide
Type "source docs/demo/real.sh --keep-plugin" Enter
Sleep 3s
Type "claude" Enter
Sleep 9s
Show

Sleep 1.5s
Type@70ms "fix the login bug, users can't sign in"
Sleep 700ms
Enter
# while Claude works, coachline writes an enhanced prompt
Sleep 30s
Escape
Sleep 2s
# Use: the enhanced prompt goes into the prompt box, [ASK] gaps in bold, for you to fill and send
Ctrl+X
Tab
Sleep 1s
Enter
Sleep 6s
