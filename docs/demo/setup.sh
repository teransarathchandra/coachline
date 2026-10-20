# Sourced (hidden) at the start of each tape in docs/demo: a throwaway Claude config with a made-up conversation (seed.py),
# a stand-in for `claude` that answers in a few seconds, and a clipboard that goes nowhere. No real data, nothing sent.
export CLAUDE_CONFIG_DIR="$(mktemp -d /tmp/claude.XXXX)"     # short, so paths the panel prints fit on one line
DEMO_DIR="$(pwd)/docs/demo"
export COACHLINE_CLAUDE="python3 $DEMO_DIR/fake_claude.py"
mkdir -p "$CLAUDE_CONFIG_DIR/bin"
for c in pbcopy wl-copy; do printf '#!/bin/sh\ncat >/dev/null\n' > "$CLAUDE_CONFIG_DIR/bin/$c"; chmod +x "$CLAUDE_CONFIG_DIR/bin/$c"; done
export PATH="$CLAUDE_CONFIG_DIR/bin:$PATH"
python3 "$DEMO_DIR/seed.py"
send() { python3 "$DEMO_DIR/seed.py" --send "$@"; }
panel() { python3 scripts/watch.py; }
export PS1='$ '
clear
