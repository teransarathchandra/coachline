# Records the hint GIF with the real Claude Code and the real coachline (installed by install.tape), at twice the GIF's size: a vague
# draft gets a meter and what it lacks under the prompt box; naming a file and a done-when fills the meter. Nothing is sent.
# Run from the repo root after install.tape, then: vhs docs/demo/hint.tape && python3 docs/demo/zoom.py docs/demo/hint.zoom.json
Output docs/demo/.rec/hint.mp4
Source docs/demo/common.tape
Source docs/demo/hires.tape

Hide
Type "source docs/demo/real.sh --keep-plugin" Enter
Sleep 3s
Type "claude" Enter
Sleep 9s
Show

Sleep 1.5s
Type@70ms "fix it now please"
# a pause: the line under the box shows the meter and the one thing the draft lacks
Sleep 4s
Type@60ms " in src/auth/login.js, the password check fails"
Sleep 4s
Type@60ms ", done when the login test passes"
Sleep 5s
