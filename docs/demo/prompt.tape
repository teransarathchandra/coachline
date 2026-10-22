# Records the prompt GIF with the real Claude Code and the real coachline (installed by install.tape), on the demo login's
# subscription, at twice the GIF's size. Run from the repo root after install.tape, then zoom in on the result:
#   vhs docs/demo/prompt.tape && python3 docs/demo/zoom.py docs/demo/prompt.zoom.json
Output docs/demo/.rec/prompt.mp4
Source docs/demo/common.tape
Source docs/demo/hires.tape

Hide
Type "source docs/demo/real.sh --keep-plugin" Enter
Sleep 3s
# no edits or shell: a file Claude changes opens Claude Code's own diff pane in coachline's place
Type "claude --disallowed-tools 'Edit,Write,NotebookEdit,Bash'" Enter
Sleep 9s
Show

Sleep 1.5s
Type@70ms "fix the login bug, users can't sign in"
Sleep 700ms
Enter
# Claude Code starts on the task; beside it, coachline analyses the prompt and shows how to make it better
Sleep 30s
