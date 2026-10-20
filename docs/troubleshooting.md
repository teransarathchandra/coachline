# Troubleshooting

Start with `/coach doctor`. It checks that your history can be read, that Python works and that the `claude` CLI is on your `PATH`, and it says how to switch each setting.

| Problem | Fix |
|---|---|
| The panel doesn't open on macOS or Linux | It needs Claude Code 2.1.287 or newer. With an older one, run `/coach watch` and paste the command into a split terminal. It opens at session start from 144 columns, otherwise with your first prompt. |
| The panel doesn't open on Windows | Run `/coach auto-open on`. The split needs Windows Terminal; in any other terminal, use `/coach watch`. |
| `python3` prints nothing on Windows | That is the Microsoft Store stub. Install Python from python.org, or use `python` or `py -3`. |
| Every prompt shows `!` and nothing is analysed | Claude analysis is off: `/coach panel-ai on`. Check that `claude` works in your terminal. |
| A prompt shows `×` | The analysis failed, often because of a usage limit. Press `e` to retry later. |
| Web research says it is paused | You hit a usage limit. It resumes at the reset time; `r` or `/coach discover` tries now. |
| No colour | `NO_COLOR` is set. On Windows the panel ignores the one Claude Code sets; check your user environment. |

## Known limits

- Claude Code's `history.jsonl` is not a documented format and may change. `/coach doctor` tells you if parsing breaks.
- Only Claude Code prompts are analysed, not claude.ai chats or Claude's replies.
- Suggestions are only as good as the model.
- The local hints are five keyword rules, English only.
- The Windows split was tested on Windows Terminal. `/coach watch` works in any terminal.

Still stuck? [Open an issue](https://github.com/teransarathchandra/coachline/issues/new/choose) with the output of `/coach doctor`.
