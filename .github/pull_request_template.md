## What and why

## How it was tested

- [ ] `python -W error::ResourceWarning -m unittest discover -s tests`
- [ ] `claude plugin test .` (if `hooks/` changed)
- [ ] A test that failed before this change and passes after it
- [ ] Snapshots updated on purpose (`UPDATE_SNAPSHOTS=1`), if the panel looks different
- [ ] `CHANGELOG.md` updated under `## Unreleased`
