# Security policy

## Supported versions

Only the latest release gets fixes. Update with `/plugin marketplace update coachline`.

## Reporting a vulnerability

Please **don't open a public issue**. Report it privately through GitHub's
[security advisories](https://github.com/teransarathchandra/coachline/security/advisories/new)
for this repository. Include steps to reproduce, your OS and the coachline version (`claude plugin list` shows it).

You'll get an acknowledgement within a few days. Fixes are released as a new version and noted in the CHANGELOG.

## Scope

In scope: anything that sends prompt text, secrets, pasted content, code or paths to Claude or the web that [docs/privacy.md](docs/privacy.md) says is not sent; that lets prompt or web content run commands or write files outside `~/.claude`; or that lets a web suggestion reach the enhanced prompt without passing the local checks.

## How coachline protects you

- It runs only on your machine and talks to Claude only through the `claude` CLI you are signed in to. No API key, no server, no telemetry.
- Prompts are redacted (emails, keys, tokens, secrets) before they are sent; pasted content never is, and projects in `llm-off.txt` are never sent.
- Web research sends a generic topic, public framework names and versions, and your installed skill names, never your prompt, code or paths.
- Model output is data: names, counts and links are checked locally, and a drafted skill is installed only when you press `s`, never overwriting an existing one.
