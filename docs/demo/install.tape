# Records docs/assets/install.gif. Run from the repo root: vhs docs/demo/install.tape
Output docs/assets/install.gif
Source docs/demo/common.tape
Set Width 1400
Set Height 620
Set FontSize 14

Hide
Type "DEMO_WORLD=--fresh source docs/demo/setup.sh && split" Enter
Sleep 1.5s
Type "claude" Enter
Sleep 1s
Show

Sleep 1s
Type@45ms "/plugin marketplace add teransarathchandra/coachline"
Sleep 500ms
Enter
Sleep 1.5s
Type@45ms "/plugin install coachline@coachline"
Sleep 500ms
Enter
Sleep 2s
# restart Claude Code: the panel opens beside it
Type@60ms "/exit"
Enter
Sleep 600ms
Type@60ms "claude"
Enter
Sleep 4s
