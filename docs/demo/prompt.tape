# Records docs/assets/prompt.gif. Run from the repo root: vhs docs/demo/prompt.tape
Output docs/assets/prompt.gif
Source docs/demo/common.tape
Set Width 1400
Set Height 620
Set FontSize 14

Hide
Type "DEMO_WORLD=--fresh source docs/demo/setup.sh && installed && split" Enter
Sleep 1.5s
Type "claude" Enter
Sleep 2s
Show

Sleep 1.5s
Type@70ms "fix the login bug, users can't sign in"
Sleep 700ms
Enter
# the panel picks the prompt up, Claude analyses it, and the card fills in
Sleep 7s
# over to the panel, and copy the enhanced prompt
Ctrl+B
Right
Sleep 400ms
Type "c"
Sleep 3.5s
