# Records the Use GIF with the real Claude Code and the real coachline (installed by install.tape), at twice the GIF's size: a vague
# prompt is analysed, then Use puts the enhanced prompt in the prompt box with its [ASK] gaps in bold. Nothing is sent by Use.
# Run from the repo root after install.tape, then: vhs docs/demo/use.tape && python3 docs/demo/zoom.py docs/demo/use.zoom.json
# The pane's Use is a Button: in the terminal, the chord ctrl+x tab gives the pane the keys (with no pause between them), one more
# Tab puts the focus ring on Use, and Enter presses it. Checked on Claude Code 2.1.308.
Output docs/demo/.rec/use.mp4
Source docs/demo/common.tape
Source docs/demo/hires.tape

Hide
Type "source docs/demo/real.sh --keep-plugin" Enter
Sleep 3s
# no edits or shell: a file Claude changes opens Claude Code's own diff pane, which ctrl+x tab would then focus instead
Type "claude --disallowed-tools 'Edit,Write,NotebookEdit,Bash'" Enter
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
Sleep 600ms
Tab
Sleep 1.2s
Enter
Sleep 7s
