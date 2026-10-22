# Records docs/assets/library.gif: the Library in the standalone panel, with made-up chats and saved prompts (setup.sh, seed.py).
# Run from the repo root: vhs docs/demo/library.tape
Output docs/assets/library.gif
Source docs/demo/common.tape

Hide
Type "source docs/demo/setup.sh" Enter
Sleep 1s
Type "panel" Enter
Sleep 1s
Show

Sleep 1.5s
# the prompts that worked first time in this project
Type "l"
Sleep 3s
# choose one and copy it, to paste in Claude Code
Type "j"
Sleep 1.2s
Type "j"
Sleep 1.2s
Type "c"
Sleep 3s
# back to the card
Type "l"
Sleep 2s
