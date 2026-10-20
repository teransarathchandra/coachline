# Sourced (hidden) at the start of each tape in docs/demo, and again as the rc file of the shell inside the demo's tmux.
# A throwaway Claude config with made-up chats (seed.py), a stand-in for `claude -p` that answers in a few seconds, a clipboard
# that goes nowhere, and `claude`, a bare stand-in for the Claude Code prompt (claude_stand_in.py). No real data, nothing sent.
DEMO_DIR="${DEMO_DIR:-$(pwd)/docs/demo}"
if [ -z "$DEMO_SEEDED" ]; then
    export DEMO_DIR DEMO_SEEDED=1
    export CLAUDE_CONFIG_DIR="$(mktemp -d /tmp/claude.XXXX)"     # short, so paths the panel prints fit on one line
    export COACHLINE_CLAUDE="python3 $DEMO_DIR/fake_claude.py"
    mkdir -p "$CLAUDE_CONFIG_DIR/bin"
    for c in pbcopy wl-copy; do printf '#!/bin/sh\ncat >/dev/null\n' > "$CLAUDE_CONFIG_DIR/bin/$c"; chmod +x "$CLAUDE_CONFIG_DIR/bin/$c"; done
    export PATH="$CLAUDE_CONFIG_DIR/bin:$PATH"
    python3 "$DEMO_DIR/seed.py" ${DEMO_WORLD:-}
fi
send() { python3 "$DEMO_DIR/seed.py" --send "$@"; }
panel() { python3 scripts/watch.py; }
claude() { python3 "$DEMO_DIR/claude_stand_in.py"; }
installed() { touch "$CLAUDE_CONFIG_DIR/demo-installed"; }
split() { tmux -L coachline-demo kill-server 2>/dev/null; tmux -L coachline-demo -f "$DEMO_DIR/tmux.conf" new-session -s demo "bash --rcfile $DEMO_DIR/setup.sh"; }
export PS1='$ '
clear
