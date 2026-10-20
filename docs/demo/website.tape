# Records the website GIF: a prompt to build a shoe store site, and coachline's suggestions for it: what to add, skills and plugins
# to use, and tools and reference sites found on the web. Real Claude Code, demo login, twice the GIF's size. Run from the repo root
# after install.tape, then zoom in on the pane:
#   vhs docs/demo/website.tape && python3 docs/demo/zoom.py docs/demo/website.zoom.json
Output docs/demo/.rec/website.mp4
Source docs/demo/common.tape
Source docs/demo/hires.tape

Hide
Type "source docs/demo/real.sh --keep-plugin" Enter
Sleep 3s
# a plugin a new user may well have, so coachline can point at it
Type "claude plugin install frontend-design@claude-plugins-official >/dev/null 2>&1; clear" Enter
Sleep 12s
Type "claude" Enter
Sleep 9s
Show

Sleep 1.5s
Type@60ms "make a website for my shoe store, modern and premium"
Sleep 700ms
Enter
# the analysis comes in about 20 seconds, the web research up to a minute later
Sleep 80s
# focus the pane (ctrl+x tab) and scroll to what the web research found
Ctrl+X
Tab
Sleep 1s
PageDown
Sleep 10s
