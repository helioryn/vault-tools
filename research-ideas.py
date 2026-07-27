#!/opt/homebrew/bin/python3
"""
research-ideas.py — Analyze vault content for unexplored project ideas.

Uses the OpenCode API key (or OpenAI API key) to identify gaps and
suggest project ideas you haven't considered.

Usage:
  research-ideas.py                     # full analysis, ask LLM
  research-ideas.py --local             # local analysis only (no LLM)
  research-ideas.py --tags tag1,tag2    # focus on specific tags
  research-ideas.py --count 10          # number of ideas (default 5)
  research-ideas.py --prompt "..."      # custom prompt
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
EXCLUDED_DIRS = {'.git', '.obsidian', 'scripts', 'archive', '18-Index'}


def parse_frontmatter(text):
    m = re.match(r'^---\s*\n(.*?)\n(?:---|\.\.\.)\s*\n', text, re.DOTALL)
    if not m:
        return {}, text
    fm_text = m.group(1)
    body = text[m.end():]

    fm = {}
    current_key = None
    current_list = []
    in_list = False

    for line in fm_text.split('\n'):
        kv_match = re.match(r'^(\w[\w_-]*)\s*:\s*(.*?)$', line)
        if kv_match:
            if in_list and current_key:
                fm[current_key] = current_list if len(current_list) > 1 else (
                    current_list[0] if current_list else ''
                )
                current_list = []
                in_list = False
            key = kv_match.group(1)
            val = kv_match.group(2).strip()
            current_key = key
            if val in ('', '[]'):
                in_list = True
                current_list = []
            elif val.startswith('[') and val.endswith(']'):
                inner = val[1:-1]
                fm[key] = [x.strip().strip('"').strip("'") for x in inner.split(',')]
                current_key = None
            else:
                fm[key] = val.strip('"').strip("'")
                current_key = None
        elif in_list and re.match(r'^\s*-\s', line):
            item = re.sub(r'^\s*-\s*', '', line).strip()
            current_list.append(item)
        elif line.strip() == '':
            continue
        else:
            if in_list and current_key:
                fm[current_key] = current_list if len(current_list) > 1 else (
                    current_list[0] if current_list else ''
                )
                current_list = []
                in_list = False
            current_key = None

    if in_list and current_key:
        fm[current_key] = current_list if len(current_list) > 1 else (
            current_list[0] if current_list else ''
        )

    return fm, body


def collect_notes():
    notes = []
    for path in VAULT.rglob('*.md'):
        parts = path.relative_to(VAULT).parts
        if any(part in EXCLUDED_DIRS for part in parts):
            continue
        text = path.read_text()
        fm, body = parse_frontmatter(text)

        m = re.search(r'^# (.+)$', text, re.MULTILINE)
        title = m.group(1).strip() if m else path.stem

        tags = fm.get('tags', [])
        if isinstance(tags, str):
            tags = [t.strip().lower() for t in tags.split(',')]

        first_para = ''
        for para in body.strip().split('\n\n'):
            clean = para.strip()
            if clean and not clean.startswith('#') and not clean.startswith('---'):
                first_para = clean[:300]
                break

        # Extract H2 headings as sub-topics
        h2s = re.findall(r'^## (.+)$', body, re.MULTILINE)

        # Extract [[links]]
        links = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', body)

        rel_path = str(path.relative_to(VAULT))
        notes.append({
            'path': rel_path,
            'title': title,
            'tags': tags,
            'h2s': h2s,
            'links': links,
            'first_para': first_para,
            'dir': str(path.parent.relative_to(VAULT)),
        })
    return notes


def build_profile(notes):
    all_tags = Counter()
    tag_notes = defaultdict(list)
    dirs = Counter()
    h2s = Counter()

    for n in notes:
        for t in n['tags']:
            all_tags[t] += 1
            tag_notes[t].append(n['title'])
        dirs[n['dir']] += 1
        for h in n['h2s']:
            h2s[h] += 1

    return {
        'total_notes': len(notes),
        'top_tags': all_tags.most_common(30),
        'top_headings': h2s.most_common(20),
        'tag_clusters': {t: sorted(titles, key=str.lower)[:10] for t, titles in tag_notes.items()},
        'areas': sorted(dirs.keys()),
    }


def build_corpus_summary(notes, max_notes=100):
    lines = []
    for n in notes[:max_notes]:
        tags_str = ', '.join(n['tags']) if n['tags'] else '(none)'
        snippet = n['first_para'][:150].replace('\n', ' ')
        lines.append(f"- [[{n['path']}|{n['title']}]]  tags=[{tags_str}]  area={n['dir']}")
        if snippet:
            lines.append(f"  {snippet}")
    return '\n'.join(lines)


OPENCODE_API_URL = "https://opencode.ai/zen/go/v1"


def get_opencode_key() -> str | None:
    auth_path = Path.home() / ".local" / "share" / "opencode" / "auth.json"
    try:
        if auth_path.exists():
            data = json.loads(auth_path.read_text())
            for val in data.values():
                if isinstance(val, str) and val.startswith("sk-"):
                    return val
                if isinstance(val, dict):
                    for v in val.values():
                        if isinstance(v, str) and v.startswith("sk-"):
                            return v
    except (json.JSONDecodeError, OSError):
        pass
    key = os.environ.get("OPENCODE_API_KEY")
    if key:
        return key
    return None


def get_llm():
    key = get_opencode_key()
    if not key:
        return None
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=os.environ.get("LLM_MODEL", "deepseek-v4-pro"),
        api_key=key,
        base_url=OPENCODE_API_URL,
        temperature=0.7,
        timeout=120,
    )


def call_llm(prompt):
    llm = get_llm()
    if not llm:
        return "No API key configured"
    try:
        return llm.invoke(prompt).content
    except Exception as e:
        return f"Error calling LLM: {e}"


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Research idea generator')
    parser.add_argument('--local', action='store_true', help='Local analysis only (no LLM)')
    parser.add_argument('--tags', type=str, help='Comma-separated tags to focus on')
    parser.add_argument('--count', type=int, default=5, help='Number of ideas (default 5)')
    parser.add_argument('--prompt', type=str, help='Custom prompt for idea generation')
    args = parser.parse_args()

    print(f'Scanning vault: {VAULT}')
    notes = collect_notes()
    profile = build_profile(notes)

    print(f'\nVault profile:')
    print(f'  Notes:     {profile["total_notes"]}')
    print(f'  Areas:     {len(profile["areas"])}')
    print(f'  Top tags:  {[t for t, c in profile["top_tags"][:10]]}')
    print(f'  Top H2s:   {[h for h, c in profile["top_headings"][:10]]}')
    print()

    if args.local:
        print('─── Local Analysis (no LLM) ───')
        print(f'\nYour vault covers {len(profile["areas"])} areas with'
              f' {len(profile["top_tags"])} unique tags.')
        print('Run without --local to get LLM-powered project idea suggestions.')
        return

    key = get_opencode_key()
    if not key:
        print('No OpenCode API key found. Check ~/.local/share/opencode/auth.json')
        print('or set OPENCODE_API_KEY. Run with --local for a basic analysis.')
        sys.exit(1)

    summary = build_corpus_summary(notes)
    focus_filter = f'\nFocus specifically on ideas related to these tags: {args.tags}' if args.tags else ''

    prompt = args.prompt or (
        'You are analyzing a personal knowledge vault. The user has notes organized '
        'in these areas with these tags and topics. Analyze what they have explored '
        f'and suggest {args.count} project ideas that connect concepts they haven\'t '
        'thought to combine yet.\n\n'
        'For each idea, explain:\n'
        '1. What concepts from the vault it connects\n'
        '2. Why it\'s novel/unexpected\n'
        '3. A concrete first step to explore it\n\n'
        'Corpus summary (title, tags, area, snippet):\n'
        f'{summary}'
        f'{focus_filter}'
    )

    print('Analyzing vault content for unexplored connections...')
    print()
    result = call_llm(prompt)
    print(result)


if __name__ == '__main__':
    main()
