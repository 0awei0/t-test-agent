# Context Summarizer

Summarize large MR context for a testing agent.

Keep:
- MR title, branches, and intent clues.
- Changed files grouped by area.
- Risk hunks for source, tests, config, CI, and browser/E2E changes.
- Existing or likely test commands.
- Dependency or environment requirements.

Avoid:
- Secrets, tokens, webhook URLs, private logs, and full raw diffs.
- Mechanical head/tail truncation as the only summary.
