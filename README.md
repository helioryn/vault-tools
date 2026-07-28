# Vault Tools

Obsidian vault utilities

## Scripts

### `vault-hygiene.py`
Comprehensive vault maintenance — frontmatter audit/fix, broken link detection, unlinked mention scanning.

```bash
python3 vault-hygiene.py              # dry-run
python3 vault-hygiene.py --fix        # apply frontmatter fixes
python3 vault-hygiene.py --broken-links  # scan only
python3 vault-hygiene.py --unlinked     # scan only
```

### `research-ideas.py`
LLM-powered gap analysis. Scans your vault content and uses the OpenCode API to suggest project ideas connecting concepts you haven't combined yet.

```bash
python3 research-ideas.py --count 5     # generate ideas
python3 research-ideas.py --local       # local analysis (no LLM)
python3 research-ideas.py --tags graph-engineering,ai  # focus area
```

Requires an OpenCode API key at `~/.local/share/opencode/auth.json` or `OPENCODE_API_KEY`.

### `process-inbox.py`
Interactive inbox processor — shows each item from `00-Inbox/` and prompts where to file it.

```bash
python3 process-inbox.py
```
