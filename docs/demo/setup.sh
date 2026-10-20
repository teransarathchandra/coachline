# Sourced (hidden) by browse.tape and patterns.tape, which record the standalone panel (/coach watch): a throwaway Claude config
# with made-up chats (seed.py), a stand-in for `claude -p` (fake_claude.py) and a clipboard that goes nowhere. No real data, nothing
# sent. install.tape and prompt.tape record the real Claude Code instead (real.sh).
DEMO_DIR="${DEMO_DIR:-$(pwd)/docs/demo}"
if [ -z "$DEMO_SEEDED" ]; then
    export DEMO_DIR DEMO_SEEDED=1
    export CLAUDE_CONFIG_DIR="$(mktemp -d /tmp/claude.XXXX)"     # short, so paths the panel prints fit on one line
    export COACHLINE_CLAUDE="python3 $DEMO_DIR/fake_claude.py"
    mkdir -p "$CLAUDE_CONFIG_DIR/bin"
    for c in pbcopy wl-copy; do printf '#!/bin/sh\ncat >/dev/null\n' > "$CLAUDE_CONFIG_DIR/bin/$c"; chmod +x "$CLAUDE_CONFIG_DIR/bin/$c"; done
    export PATH="$CLAUDE_CONFIG_DIR/bin:$PATH"
    python3 "$DEMO_DIR/seed.py"
fi
send() { python3 "$DEMO_DIR/seed.py" --send "$@"; }
panel() { python3 scripts/watch.py; }
export PS1='$ '
clear
