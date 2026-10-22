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
  <a href="#desktop"><img src="https://img.shields.io/badge/Claude_desktop_app-Opens_by_itself-555555?style=for-the-badge&logo=claude&logoColor=white" alt="Claude desktop app: opens by itself"></a>
  <a href="#editors"><img src="https://img.shields.io/badge/VS_Code_·_Cursor_·_Windsurf-Opens_by_itself-007ACC?style=for-the-badge" alt="VS Code, Cursor, Windsurf and Antigravity: opens by itself"></a>
</p>

<img src="docs/assets/screenshot.png" alt="Claude Code with the coachline panel beside it: the prompt, what to improve, including a skill to use, and the enhanced prompt, each in its own coloured card" width="100%">

## How it works

### 1 · Install, and the panel opens beside Claude Code

Two commands in Claude Code, and coachline opens in a side panel right away. No restart, no API key.

<img src="docs/assets/install.gif" alt="In Claude Code, /plugin marketplace add and /plugin install coachline@coachline; the coachline panel opens on the right at once" width="100%">

### 2 · Type a prompt, see how to make it better

Work as usual. While Claude works on your prompt, the panel shows what to **improve** and an **enhanced prompt**, with `[ASK: …]` where only you know the answer. **Use** puts it in your prompt box; while you type, the line under the box says what your draft lacks, or that a prompt like it worked before. Those land in your **Library**.

<img src="docs/assets/prompt.gif" alt="A vague prompt is sent in Claude Code; while Claude works on it, the coachline panel shows tips and an enhanced prompt, and the view zooms in on them" width="100%">

### 3 · Starting something new? Get the skills, tools and references for it

For a new task, coachline names the **skills and plugins** you have that fit, then searches the web for **tools, docs and reference sites**, and checks each link before you see it.

<img src="docs/assets/website.gif" alt="A prompt to make a shoe store website: the panel suggests the frontend-design skill and an enhanced prompt, then web finds such as Playwright MCP, Motion for React and the WCAG 2.2 quick reference" width="100%">

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

coachline is active straight away.

<details open>
<summary><img src="https://cdn.simpleicons.org/apple/000000/ffffff" height="16" alt=""> <b>macOS</b> · <img src="https://cdn.simpleicons.org/linux/000000/ffffff" height="16" alt=""> <b>Linux</b>: nothing else to do</summary>

<br>The panel opens inside Claude Code, beside the conversation: as soon as it is installed, then at the start of every session (from 144 columns wide; narrower, with your first prompt). Needs Claude Code 2.1.287 or newer; with an older one, use `/coach watch` as described under *any terminal* below.

</details>

<details open id="desktop">
<summary><img src="https://cdn.simpleicons.org/claude/D97757" height="16" alt=""> <b>Claude desktop app</b> (macOS · Windows): nothing else to do</summary>

<br>In a Code session, the pane opens on the right with your first prompt, in the app's own look, light or dark. The app's Code sessions use the plugins you installed in Claude Code.

<img src="docs/assets/desktop.png" alt="The coachline pane in the Claude desktop app, light and dark: your prompt, Improve with its tips, and the enhanced prompt with a Copy button, each in the app's own rounded card" width="70%">

</details>

<details id="windows">
<summary><img src="docs/assets/icons/windows.svg" height="16" alt=""> <b>Windows</b>: one command</summary>

<br>In the terminal, run this once in Claude Code. From then on every session opens the panel in a Windows Terminal split, one panel per tab (the desktop app has its own pane):

```
/coach auto-open on
```

</details>

<details open id="editors">
<summary><img src="docs/assets/icons/vscode.svg" height="16" alt=""> <b>VS Code</b> · <b>Cursor</b> · <b>Windsurf</b> · <b>Antigravity</b>: nothing else to do</summary>

<br>With the Claude Code extension, the pane opens beside the Claude Code tab, in your editor's theme, light or dark. The extension uses the plugins you installed in Claude Code.

<img src="docs/assets/editor.png" alt="The coachline pane beside Claude Code in VS Code, light and dark themes: your prompt, Improve with its tips, and the enhanced prompt with a Copy button, in the editor's own cards and colours" width="70%">

</details>

<details>
<summary><img src="https://cdn.simpleicons.org/jetbrains/000000/ffffff" height="16" alt=""> <b>JetBrains</b> · any terminal</summary>

<br>Run `/coach watch` in Claude Code. It prints a one-line command: paste it into a split terminal next to Claude Code.

</details>

**Check your setup:** `/coach doctor` checks Python, the `claude` CLI and your history; `/coach setup` shows your settings.

## Keys

| | | | |
|---|---|---|---|
| `↑` `↓` | choose a prompt | `c` | copy the enhanced prompt |
| `Enter` | read it full width | `e` | analyse it now |
| `i` | patterns from past chats | `s` | install a drafted skill |
| `m` | mouse on or off | `q` | quit |

In the Claude Code pane, the desktop app and the editors, click its buttons (`[ Copy ]`, `[ Analyse ]`); the keys are for the standalone panel (Windows and `/coach watch`). Every key, mark and `/coach` command: [usage guide](docs/usage.md).

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
