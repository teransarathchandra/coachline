<p align="center">
  <img src="docs/assets/banner.svg" alt="coachline: a side panel for Claude Code that coaches every prompt" width="100%">
</p>

<p align="center">
  <a href="https://github.com/teransarathchandra/coachline/releases"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fteransarathchandra%2Fcoachline%2Fmain%2F.claude-plugin%2Fplugin.json&query=%24.version&label=version&color=d97757" alt="Version"></a>
  <a href="https://github.com/teransarathchandra/coachline/actions/workflows/ci.yml"><img src="https://github.com/teransarathchandra/coachline/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-%E2%89%A53.9-3776ab?logo=python&logoColor=white" alt="Python 3.9 or newer">
  <img src="https://img.shields.io/badge/dependencies-none-2ea44f" alt="No dependencies">
  <img src="https://img.shields.io/badge/API_key-not_needed-2ea44f" alt="No API key needed">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license"></a>
</p>

<p align="center">
  coachline sits next to <b>Claude Code</b>, shows the prompts of your conversation, says how each one could be better<br>
  and hands you an enhanced version to copy. Claude does the analysis on <b>your own subscription</b>.
</p>

<p align="center">
  <a href="#install"><img src="https://img.shields.io/badge/Claude_Code-Install_plugin-D97757?style=for-the-badge&logo=claude&logoColor=white" alt="Install in Claude Code"></a>
  <a href="#install"><img src="https://img.shields.io/badge/macOS_·_Linux-Opens_by_itself-555555?style=for-the-badge&logo=apple&logoColor=white" alt="macOS and Linux: opens by itself"></a>
  <a href="#windows"><img src="https://img.shields.io/badge/Windows-Terminal_split-0078D4?style=for-the-badge" alt="Windows: Windows Terminal split"></a>
</p>


## How it works

### 1 · Install, and the panel opens beside Claude Code

Two commands in Claude Code. After a restart, coachline opens in a side panel by itself.

<img src="docs/assets/install.gif" alt="The two /plugin commands are typed in Claude Code; after a restart the coachline panel opens on the right" width="100%">

### 2 · Type a prompt, see how to make it better

Work as usual. The panel picks up each prompt and shows what to **improve** and an **enhanced prompt**. Press `c` to copy it and fill in the `[ASK: …]` parts.

<img src="docs/assets/prompt.gif" alt="A vague prompt is typed in Claude Code; the panel analyses it and shows tips and an enhanced prompt, which is copied with c" width="100%">

<details>
<summary><b>More:</b> browse the whole thread, and patterns from your past chats</summary>

<br>`↑` `↓` move through the conversation. Each prompt keeps its card, with links Claude found on the web and **checked on your machine** first.

<img src="docs/assets/browse.gif" alt="Moving back through the thread shows each prompt's card, its web finds and the full prompt" width="100%">

`i` shows the habits and repeated requests Claude spotted in your history. `s` turns a repeated request into a skill.

<img src="docs/assets/patterns.gif" alt="Patterns from past chats, then the drafted skill is installed with s" width="100%">

</details>

## Install

You need [Claude Code](https://claude.com/claude-code) (signed in, `claude` works in your terminal) and **Python 3.9+**. In Claude Code:

```
/plugin marketplace add teransarathchandra/coachline
/plugin install coachline@coachline
```

Then restart Claude Code.

<details open>
<summary><img src="https://cdn.simpleicons.org/apple/000000/ffffff" height="16" alt=""> <b>macOS</b> · <img src="https://cdn.simpleicons.org/linux/000000/ffffff" height="16" alt=""> <b>Linux</b>: nothing else to do</summary>

<br>The panel opens inside Claude Code at the start of a session (from 144 columns wide, otherwise with your first prompt). Needs Claude Code 2.1.287 or newer; with an older one, use `/coach watch` as described under *any terminal* below.

</details>

<details id="windows">
<summary><img src="docs/assets/icons/windows.svg" height="16" alt=""> <b>Windows</b>: one command</summary>

<br>Run this once in Claude Code. From then on every session opens the panel in a Windows Terminal split, one panel per tab:

```
/coach auto-open on
```

</details>

<details>
<summary><img src="docs/assets/icons/vscode.svg" height="16" alt=""> <b>VS Code</b> · <img src="https://cdn.simpleicons.org/jetbrains/000000/ffffff" height="16" alt=""> <b>JetBrains</b> · any terminal</summary>

<br>Run `/coach watch` in Claude Code. It prints a one-line command: paste it into a split terminal (VS Code: *Terminal → Split Terminal*) next to Claude Code.

</details>

**Check your setup:** `/coach doctor` checks Python, the `claude` CLI and your history; `/coach setup` shows your settings.

## Keys

| | | | |
|---|---|---|---|
| `↑` `↓` | choose a prompt | `c` | copy the enhanced prompt |
| `Enter` | read it full width | `e` | analyse it now |
| `i` | patterns from past chats | `s` | install a drafted skill |
| `m` | mouse on or off | `q` | quit |

Every key, mark and `/coach` command: [usage guide](docs/usage.md).

## Private by design

- 🔑 **No API key.** Claude runs through your own Claude Code login, and there's no telemetry.
- 🧹 **Redacted first.** Emails, keys and tokens are removed and pasted text is never sent. List a project in `~/.claude/coach/llm-off.txt` to keep it out entirely.
- ✅ **Checked on your machine.** Counts are recomputed, skill names must exist, and every link must load before you see it.
- 🔌 **Off in one command.** `/coach panel-ai off` keeps only the built-in local hints.

What is sent and when: [privacy](docs/privacy.md).

## Documentation

[Usage](docs/usage.md) · [Privacy and accuracy](docs/privacy.md) · [Troubleshooting](docs/troubleshooting.md) · [Changelog](CHANGELOG.md)

## Contributing

Issues and pull requests are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). Security reports go through [SECURITY.md](SECURITY.md).

[MIT](LICENSE) © Teran Sarathchandra
