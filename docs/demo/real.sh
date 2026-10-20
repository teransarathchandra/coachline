# Sourced (hidden) by install.tape, prompt.tape and website.tape, which record the real Claude Code. It uses a separate config that holds only a
# demo login, so none of your own history, settings or plugins appear. Sign in to it once:
#   CLAUDE_CONFIG_DIR=~/.claude-coachline-demo claude auth login
# Each take starts like a new user: coachline is uninstalled and its state and history cleared, in that demo config only.
# a recording started from inside Claude Code inherits its session markers, which would make this one a child session
for v in $(env | grep -oE '^(CLAUDECODE|CLAUDE_[A-Z_]+|AI_AGENT|GIT_EDITOR)=' | tr -d =); do unset "$v"; done
export CLAUDE_CONFIG_DIR="${COACHLINE_DEMO_CONFIG:-$HOME/.claude-coachline-demo}"
case "$CLAUDE_CONFIG_DIR" in "$HOME/.claude"|"$HOME/.claude/") echo "refusing to reset your own Claude config" >&2; return 1 ;; esac
if [ "$1" != "--keep-plugin" ]; then
    claude plugin uninstall coachline@coachline >/dev/null 2>&1
    claude plugin marketplace remove coachline >/dev/null 2>&1
fi
rm -rf "$CLAUDE_CONFIG_DIR/coach" "$CLAUDE_CONFIG_DIR/history.jsonl"
# a tiny project to work in, with the login bug the prompt GIF asks about
DEMO_PROJECT=/tmp/shoe-shop
rm -rf "$DEMO_PROJECT"; mkdir -p "$DEMO_PROJECT/src/auth"
printf 'export async function login(email, password) {\n  const user = await db.users.find({ email });\n  return user && user.password == password;\n}\n' > "$DEMO_PROJECT/src/auth/login.js"
printf '{ "name": "shoe-shop", "private": true }\n' > "$DEMO_PROJECT/package.json"
git -C "$DEMO_PROJECT" init -q -b main && git -C "$DEMO_PROJECT" add -A && git -C "$DEMO_PROJECT" -c user.name=demo -c user.email=demo@example.com commit -qm init
cd "$DEMO_PROJECT"
export PS1='$ '
clear
