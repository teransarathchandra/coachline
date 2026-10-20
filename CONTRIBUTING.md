# Contributing

Thanks for helping improve coachline. By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Setup

coachline is plain Python 3.9+ with no dependencies, plus one TypeScript module for the Claude Code pane. Clone the repo and run:

```bash
python -W error::ResourceWarning -m unittest discover -s tests   # the Python suite (what CI runs)
claude plugin test .                                             # the pane module (hooks/coachline.test.ts)
claude plugin validate .                                         # the manifests and hooks
```

To try your copy in Claude Code: `/plugin marketplace add /path/to/coachline`, then `/plugin install coachline@coachline`.

## Project layout

| Path | What's there |
|---|---|
| `scripts/` | Everything the plugin runs: `watch.py` (the panel), `pane.py` (the Claude Code pane's data), `coach.py` (shared core, `/coach`), `advisor.py` (fast pass), `discover.py` (web research), `review.py` (history patterns) |
| `hooks/` | Session-start hooks and the pane module `coachline.tsx` |
| `skills/coach/` | The `/coach` skill |
| `tests/` | unittest suite; `tests/fake_claude.py` stands in for `claude -p`, `tests/snapshots/` holds every panel screen |
| `docs/` | User docs, GIFs (`docs/assets/`) and the scripts that record them (`docs/demo/`) |

## How changes are made

- **Tests first.** Every behaviour change comes with a test that fails before it and passes after. Tests never call the real `claude`: set `COACHLINE_CLAUDE` to `tests/fake_claude.py`, and `COACHLINE_CLIPBOARD` instead of touching the real clipboard.
- **Screens are snapshots.** If you change how the panel looks on purpose, run `UPDATE_SNAPSHOTS=1 python -m unittest tests.test_snapshots` and review the diff in `tests/snapshots/`.
- **Nothing leaves the machine unredacted.** Anything new sent to Claude goes through `coach.redact`, honours `llm-off.txt`, and is described in [docs/privacy.md](docs/privacy.md).
- **Check what Claude says.** Names, counts and links from a model are verified locally before they are shown.
- **Standard library only**, and it must work on Windows, macOS and Linux.
- If you change the suggestion engine, compare `python scripts/eval_suggest.py --yes` before and after (it uses your Claude subscription and is not run in CI).

## Pull requests

- One topic per PR, with what changed and why.
- CI (Ubuntu, macOS and Windows on Python 3.9 and 3.13) must pass.
- Add a line to `CHANGELOG.md` under `## Unreleased`.

## Re-recording the GIFs

The GIFs in `docs/assets/` are recorded with [VHS](https://github.com/charmbracelet/vhs).

- `install.tape` and `prompt.tape` record the **real Claude Code**: they install coachline from GitHub `main` and send one prompt in a throwaway project (`/tmp/shoe-shop`). They run in a separate Claude config that holds only a demo login, so none of your own history, settings or plugins appear (`docs/demo/real.sh`). Sign in to it once, and record after merging, as the install comes from GitHub:

  ```bash
  CLAUDE_CONFIG_DIR=~/.claude-coachline-demo claude auth login
  vhs docs/demo/install.tape && vhs docs/demo/prompt.tape     # a few calls on that login's subscription
  ```

- `browse.tape` and `patterns.tape` record the standalone panel in a temporary config with made-up chats (`docs/demo/seed.py`) and a stand-in for `claude -p` (`docs/demo/fake_claude.py`), so nothing is sent:

  ```bash
  vhs docs/demo/browse.tape && vhs docs/demo/patterns.tape
  ```

## Releasing (maintainer)

1. In a PR, set the new version in `.claude-plugin/plugin.json` and move the `## Unreleased` notes under `## <version> (<date>)` in `CHANGELOG.md`.
2. After merge, on an up-to-date `main`: `claude plugin tag --push`. It checks the manifests agree and pushes the tag `coachline--v<version>`.
3. The Release workflow checks the tag against `plugin.json`, runs the tests and creates the GitHub release with that version's CHANGELOG notes.

Users get the new version through `/plugin marketplace update coachline` (or automatically, if they turned on auto-update for the marketplace).

## Reporting security issues

See [SECURITY.md](SECURITY.md). Please don't open a public issue for vulnerabilities.
