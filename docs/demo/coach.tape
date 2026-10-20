# Records docs/assets/coach.gif. Run from the repo root: vhs docs/demo/coach.tape
Output docs/assets/coach.gif
Source docs/demo/common.tape

Hide
Type "source docs/demo/setup.sh" Enter
Sleep 1s
# you send a new prompt in Claude Code a moment after the panel opens
Type `(sleep 2.5; send "the product page is slow, speed it up") >/dev/null 2>&1 & panel` Enter
Sleep 1s
Show

# the new prompt is analysed in the background: the spinner turns, then the card fills
Sleep 7.5s
Type "c"
Sleep 3s
