# Records docs/assets/install.gif with the real Claude Code, installing coachline from GitHub. Needs the one-time demo login in
# docs/demo/real.sh. Run from the repo root: vhs docs/demo/install.tape
Output docs/assets/install.gif
Source docs/demo/common.tape
Set Width 1400
Set Height 860
Set FontSize 14

Hide
Type "source docs/demo/real.sh" Enter
Sleep 8s
Type "claude" Enter
Sleep 7s
Show

Sleep 1.5s
Type@45ms "/plugin marketplace add teransarathchandra/coachline"
Sleep 600ms
Enter
Sleep 3s
# the clone takes ~20s on a slow line; cut the wait from the GIF, not the check
Hide
Wait+Screen@120s /Successfully added marketplace/
Show
Sleep 2s
Type@45ms "/plugin install coachline@coachline"
Sleep 600ms
Enter
Sleep 3s
# install for you (user scope): coachline is active at once and its panel opens
Enter
Sleep 9s
