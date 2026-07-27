#!/opt/homebrew/bin/python3
"""
process-inbox.py — Interactive inbox processing for Obsidian vault.

Scans 00-Inbox/, shows each item, prompts for destination, moves it,
updates frontmatter, and updates the destination _index.md.
"""

import re
import sys
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
INBOX = VAULT / '00-Inbox'

DESTINATIONS = {
    'p': ('project', '07-Features', 'draft'),
    't': ('task', '06-Tasks', 'active'),
    'r': ('research', '01-Research', 'draft'),
    'd': ('decision', '05-Decisions', 'draft'),
    'k': ('knowledge', '13-Knowledge', 'draft'),
    'a': ('architecture', '02-Architecture', 'draft'),
}

HELP_TEXT = """  [p]roject      → 07-Features/
  [t]ask         → 06-Tasks/
  [r]esearch     → 01-Research/
  [d]ecision     → 05-Decisions/
  [k]nowledge    → 13-Knowledge/
  [a]rchitecture → 02-Architecture/
  [s]kip
  [?]help        show this
  [q]uit"""


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
    for key, val in fm.items():
        if isinstance(val, list):
            lines.append(f'{key}:')
            for item in val:
                lines.append(f'  - {item}')
        else:
            lines.append(f'{key}: {val}')
    lines.append('---')
    lines.append('')
    return '\n'.join(lines) + body.lstrip('\n')


def update_frontmatter(fm):
    today = date.today().isoformat()

    if isinstance(fm.get('tags'), list):
        fm['tags'] = [t for t in fm['tags'] if t not in ('inbox', 'fleeting')]
        if not fm['tags']:
            del fm['tags']
    elif isinstance(fm.get('tags'), str):
        tags = [t.strip() for t in fm['tags'].split(',')]
        tags = [t for t in tags if t not in ('inbox', 'fleeting')]
        if tags:
            fm['tags'] = tags if len(tags) > 1 else tags[0]
        else:
            del fm['tags']

    fm['updated'] = today
    return fm


def get_title(fm, text, fname):
    if fm.get('title'):
        return fm['title']
    m = re.search(r'^# (.+)$', text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return fname.stem


def show_preview(fpath):
    text = fpath.read_text()
    fm, body = parse_frontmatter(text)
    title = get_title(fm, text, fpath)

    print(f'\n{"=" * 60}')
    print(f'  File: {fpath.name}')
    print(f'  Title: {title}')
    if fm.get('tags'):
        tags = fm['tags'] if isinstance(fm['tags'], list) else [fm['tags']]
        print(f'  Tags:  {", ".join(tags)}')
    if fm.get('status'):
        print(f'  Status: {fm["status"]}')
    if fm.get('priority'):
        print(f'  Priority: {fm["priority"]}')
    if fm.get('created'):
        print(f'  Created: {fm["created"]}')
    print(f'{"=" * 60}')

    body_lines = body.strip().split('\n')
    preview = '\n'.join(body_lines[:6])
    if len(body_lines) > 6:
        preview += '\n  ...'
    print(f'{preview}')

    return text, fm, body, title


def choose_destination():
    while True:
        choice = input('  Move to? [p/t/r/d/k/a/s/?/q] ').strip().lower()
        if choice in DESTINATIONS:
            return DESTINATIONS[choice]
        elif choice == 's':
            return None
        elif choice == 'q':
            return 'QUIT'
        elif choice == '?':
            print(HELP_TEXT)
        else:
            print('  Invalid choice. Use ? for help.')


def update_index(dest_dir, note_path):
    index_path = dest_dir / '_index.md'
    if not index_path.exists():
        return

    text = index_path.read_text()
    rel_path = note_path.relative_to(VAULT)
    stem = note_path.stem
    link = f'- [[{rel_path}|{stem}]]'

    if link in text:
        return

    lines = text.rstrip().split('\n')
    lines.append(link)
    lines.append('')
    index_path.write_text('\n'.join(lines))


def main():
    inbox_files = sorted([
        f for f in INBOX.iterdir()
        if f.suffix == '.md' and f.name != '_index.md'
    ])

    if not inbox_files:
        print('Inbox is empty. Nothing to process.')
        return

    print(f'\n{" " * 23}📬 INBOX ({len(inbox_files)} items)\n')

    processed = 0
    skipped = 0

    for fpath in inbox_files:
        text, fm, body, title = show_preview(fpath)
        result = choose_destination()

        if result == 'QUIT':
            print('  Quitting.')
            break

        if result is None:
            print('  Skipped.')
            skipped += 1
            continue

        label, folder_name, new_status = result
        dest_dir = VAULT / folder_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        fm = update_frontmatter(fm)
        if fm.get('status', '') in ('inprocess', 'active', ''):
            fm['status'] = new_status

        new_content = format_frontmatter(fm, body)

        dest_path = dest_dir / fpath.name
        if dest_path.exists():
            base = dest_path.stem
            counter = 1
            while True:
                candidate = dest_dir / f'{base}-{counter}{dest_path.suffix}'
                if not candidate.exists():
                    dest_path = candidate
                    break
                counter += 1

        dest_path.write_text(new_content)
        fpath.unlink()
        update_index(dest_dir, dest_path)

        if label == 'project':
            proj_dir = Path.home() / 'Project' / title
            if not proj_dir.exists():
                create = input(f'  Create ~/Project/{title}/ directory? [y/N] ').strip().lower()
                if create == 'y':
                    proj_dir.mkdir(parents=True, exist_ok=True)
                    (proj_dir / 'README.md').write_text(f'# {title}\n\nSee [[{dest_path.relative_to(VAULT)}]].\n')
                    print(f'  Created {proj_dir}/')
            else:
                print(f'  ~/Project/{title}/ already exists')

        processed += 1
        print(f'  ✅ → {str(dest_path.relative_to(VAULT))}')

    remaining = [
        f for f in INBOX.iterdir()
        if f.suffix == '.md' and f.name != '_index.md'
    ]
    print(f'\n  Done: {processed} moved, {skipped} skipped'
          f'{"" if not remaining else f", {len(remaining)} remaining"}')

    if not inbox_files:
        pass  # already handled above
    elif not remaining and processed > 0:
        print('  Inbox is now empty.')


if __name__ == '__main__':
    main()
