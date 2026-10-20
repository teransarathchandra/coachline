# Records docs/assets/prompt.gif with the real Claude Code and the real coachline (installed by install.tape), on the demo login's
# subscription. Run from the repo root after install.tape: vhs docs/demo/prompt.tape
Output docs/assets/prompt.gif
Source docs/demo/common.tape
Set Width 1400
Set Height 860
Set FontSize 14

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
# Claude Code starts on the task; beside it, coachline analyses the prompt and shows how to make it better
Sleep 40s
