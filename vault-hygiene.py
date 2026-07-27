#!/opt/homebrew/bin/python3
"""
vault-hygiene.py — Comprehensive vault maintenance.

Usage:
  vault-hygiene.py                          # dry-run: report only
  vault-hygiene.py --fix                    # apply frontmatter fixes
  vault-hygiene.py --fix --force            # overwrite existing fields
  vault-hygiene.py --broken-links           # scan only broken links
  vault-hygiene.py --unlinked              # scan only unlinked mentions
  vault-hygiene.py --all                   # full scan + fix
"""

import re
import sys
from datetime import date, datetime
from pathlib import Path
from collections import defaultdict

VAULT = Path(__file__).resolve().parent.parent

EXCLUDED_DIRS = {'.git', '.obsidian', 'scripts', 'archive', '18-Index'}
STANDARD_FIELDS = ['title', 'created', 'modified', 'tags', 'aliases']


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


def format_frontmatter(fm, body):
    lines = ['---']
    for key in ('title', 'created', 'modified', 'aliases', 'tags', 'status', 'priority', 'type'):
        if key in fm:
            val = fm[key]
            if isinstance(val, list):
                if val:
                    lines.append(f'{key}:')
                    for item in val:
                        lines.append(f'  - {item}')
            else:
                lines.append(f'{key}: {val}')
    for key, val in fm.items():
        if key not in ('title', 'created', 'modified', 'aliases', 'tags', 'status', 'priority', 'type'):
            if isinstance(val, list):
                if val:
                    lines.append(f'{key}:')
                    for item in val:
                        lines.append(f'  - {item}')
            else:
                lines.append(f'{key}: {val}')
    lines.append('---')
    lines.append('')
    return '\n'.join(lines) + body.lstrip('\n')


def get_title(text, fpath):
    m = re.search(r'^# (.+)$', text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return fpath.stem


def collect_markdown_files():
    files = []
    for path in VAULT.rglob('*.md'):
        parts = path.relative_to(VAULT).parts
        if any(part in EXCLUDED_DIRS for part in parts):
            continue
        files.append(path)
    return sorted(files)


def extract_links(text):
    return re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', text)


def extract_note_titles():
    titles = {}
    for path in collect_markdown_files():
        text = path.read_text()
        fm, body = parse_frontmatter(text)
        title = get_title(text, path)
        titles[path.stem] = {
            'path': path,
            'title': title,
            'fm': fm,
            'text': text,
            'body': body,
        }
    return titles


def scan_broken_links(titles):
    broken = []
    alive_stems = set(titles.keys())
    for stem, info in titles.items():
        links = extract_links(info['text'])
        for link in links:
            link_stem = Path(link).stem
            if link_stem not in alive_stems:
                broken.append((str(info['path'].relative_to(VAULT)), link))
    return broken


def scan_unlinked_mentions(titles):
    unlinked = []
    alive_stems = set(titles.keys())
    for stem, info in titles.items():
        body = info['body']
        existing_links = set(extract_links(info['text']))
        for other_stem in alive_stems:
            if other_stem == stem:
                continue
            pattern = r'(?<!\[\[)' + re.escape(other_stem) + r'(?!\]\])'
            if re.search(pattern, body, re.IGNORECASE):
                other_title = titles[other_stem]['title']
                if other_title.lower() in body.lower() and other_stem not in {Path(l).stem for l in existing_links}:
                    unlinked.append((str(info['path'].relative_to(VAULT)), other_stem, other_title))
    return unlinked


def audit_frontmatter(titles, fix=False, force=False):
    today = date.today().isoformat()
    report = []
    changes = 0

    for stem, info in titles.items():
        fm = dict(info['fm'])
        text = info['text']
        body = info['body']
        dirty = False

        if fm.get('title') != info['title']:
            report.append(f"  {stem}: title field missing/mismatch → '{info['title']}'")
            if fix and (force or not fm.get('title')):
                fm['title'] = info['title']
                dirty = True

        if not fm.get('created'):
            fpath = info['path']
            created = datetime.fromtimestamp(fpath.stat().st_birthtime).date().isoformat()
            report.append(f"  {stem}: missing created → {created}")
            if fix:
                fm['created'] = created
                dirty = True

        if fix:
            fm['modified'] = today
            dirty = True

        if 'tags' in fm:
            tags = fm['tags']
            if isinstance(tags, str):
                tags_list = [t.strip().lower() for t in tags.split(',')]
            elif isinstance(tags, list):
                tags_list = [t.strip().lower() for t in tags]
            else:
                tags_list = []
            tags_list = sorted(set(tags_list))
            if tags_list != (fm['tags'] if isinstance(fm['tags'], list) else [fm['tags']]):
                report.append(f"  {stem}: normalized tags → {tags_list}")
                if fix:
                    fm['tags'] = tags_list if len(tags_list) > 1 else (tags_list[0] if tags_list else '')
                    dirty = True

        if dirty and fix:
            new_content = format_frontmatter(fm, body)
            info['path'].write_text(new_content)
            changes += 1

    return report, changes


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Vault hygiene tools')
    parser.add_argument('--fix', action='store_true', help='Apply frontmatter fixes')
    parser.add_argument('--force', action='store_true', help='Overwrite existing frontmatter fields')
    parser.add_argument('--broken-links', action='store_true', help='Scan broken links only')
    parser.add_argument('--unlinked', action='store_true', help='Scan unlinked mentions only')
    parser.add_argument('--all', action='store_true', help='Full scan + fixes')
    args = parser.parse_args()

    if not any([args.broken_links, args.unlinked, args.all]):
        args.all = True

    print(f'Vault: {VAULT}')
    print()

    titles = collect_markdown_files()
    print(f'Found {len(titles)} markdown files')
    print()

    if args.all or args.broken_links:
        print('─── Broken Links ───')
        titles_dict = extract_note_titles()
        broken = scan_broken_links(titles_dict)
        if broken:
            for file_path, link in broken:
                print(f'  {file_path} → [[{link}]]')
            print(f'  ({len(broken)} broken links)')
        else:
            print('  None found')
        print()

    if args.all or args.unlinked:
        print('─── Unlinked Mentions ───')
        if not args.all and not args.fix:
            titles_dict = extract_note_titles()
        unlinked = scan_unlinked_mentions(titles_dict)
        if unlinked:
            for file_path, stem, title in unlinked[:30]:
                print(f'  {file_path} → mentions "{title}" ([[{stem}]])')
            if len(unlinked) > 30:
                print(f'  ... and {len(unlinked) - 30} more')
            print(f'  ({len(unlinked)} total unlinked mentions)')
        else:
            print('  None found')
        print()

    if args.all or args.fix:
        print('─── Frontmatter Audit ───')
        report, changes = audit_frontmatter(titles_dict, fix=args.fix, force=args.force)
        if report:
            for line in report:
                print(line)
            if args.fix:
                print(f'  ({changes} files updated)')
            else:
                print('  (dry-run — run with --fix to apply)')
        else:
            print('  All files have clean frontmatter')
        print()

    if args.fix:
        print(f'Done — {changes} files modified.')
    else:
        print('Dry-run complete. Run with --fix to apply changes.')


if __name__ == '__main__':
    main()
