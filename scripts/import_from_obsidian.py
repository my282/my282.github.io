#!/usr/bin/env python3
"""Import an Obsidian note into this Jekyll site.

Copies a Markdown file out of an Obsidian vault into writeups/ or notes/,
rewrites Obsidian image embeds (``![[file.png]]``) into standard Markdown
image links pointing at assets/img/<section>/<slug>/, copying the actual
image files alongside, and prepends the Jekyll/Just the Docs front matter.

Usage:
    python3 scripts/import_from_obsidian.py "<path to note.md>" --section writeups
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Default Obsidian vault to search when `source` isn't an existing file path.
# Override with --vault or the OBSIDIAN_VAULT environment variable.
DEFAULT_VAULT = Path("/mnt/c/Users/myoum/Documents/leaning_memo")

IMAGE_EMBED_RE = re.compile(r"!\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
FRONT_MATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)
HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
SUSPICIOUS_FENCE_RE = re.compile(r"^```[^`\n]+```.+$")
CALLOUT_RE = re.compile(r"^>\s*\[!(\w+)\]", re.MULTILINE)


FENCED_CODE_RE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)


def slugify(name: str) -> str:
    name = re.sub(r"\s+", "-", name.strip())
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name


def extract_title(text: str, fallback: str) -> str:
    without_code = FENCED_CODE_RE.sub("", text)
    match = HEADING_RE.search(without_code)
    return match.group(1).strip() if match else fallback


def find_vault_root(note_path: Path) -> Path | None:
    for parent in [note_path.parent, *note_path.parents]:
        if (parent / ".obsidian").is_dir():
            return parent
    return None


def resolve_asset(filename: str, note_path: Path, vault_root: Path | None) -> Path | None:
    candidate = note_path.parent / "assets" / filename
    if candidate.is_file():
        return candidate
    if vault_root is not None:
        matches = list(vault_root.rglob(filename))
        if matches:
            return matches[0]
    return None


def resolve_source(source_arg: str, vault: Path) -> Path:
    """Resolve `source_arg` to a note file: an existing path, or a search term
    matched against note filenames (stem) in `vault`."""
    candidate = Path(source_arg).expanduser()
    if candidate.is_file():
        return candidate.resolve()

    if not vault.is_dir():
        print(f"error: not an existing file, and vault not found: {vault}", file=sys.stderr)
        raise SystemExit(1)

    term = source_arg.lower()
    matches = [
        p for p in vault.rglob("*.md")
        if term in p.stem.lower() and ".obsidian" not in p.parts
    ]
    if not matches:
        print(f"error: no note matching {source_arg!r} found under {vault}", file=sys.stderr)
        raise SystemExit(1)
    if len(matches) > 1:
        exact = [p for p in matches if p.stem.lower() == term]
        if len(exact) == 1:
            return exact[0].resolve()
        print(f"error: multiple notes match {source_arg!r}, be more specific:", file=sys.stderr)
        for p in matches:
            print(f"  - {p}", file=sys.stderr)
        raise SystemExit(1)
    return matches[0].resolve()


def compute_nav_order(section_dir: Path, override: int | None) -> int:
    if override is not None:
        return override
    max_order = 0
    for md in list(section_dir.glob("*.md")) + list(section_dir.glob("*.markdown")):
        if md.stem == "index":
            continue
        text = md.read_text(encoding="utf-8", errors="ignore")
        fm_match = FRONT_MATTER_RE.match(text)
        if not fm_match:
            continue
        order_match = re.search(r"^nav_order:\s*(\d+)", fm_match.group(0), re.MULTILINE)
        if order_match:
            max_order = max(max_order, int(order_match.group(1)))
    return max_order + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        help="Path to the Obsidian .md note, or a (partial) note filename to search "
             "for in the vault",
    )
    parser.add_argument("--section", required=True, choices=["writeups", "notes"])
    parser.add_argument("--slug", help="Override the destination filename/slug")
    parser.add_argument("--nav-order", type=int, help="Override the nav_order")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing destination file")
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path(os.environ.get("OBSIDIAN_VAULT", DEFAULT_VAULT)),
        help="Obsidian vault root to search when `source` isn't an existing file path",
    )
    args = parser.parse_args()

    source = resolve_source(args.source, args.vault.expanduser())

    text = source.read_text(encoding="utf-8")
    text = FRONT_MATTER_RE.sub("", text, count=1)

    title = extract_title(text, fallback=source.stem)

    slug = slugify(args.slug or source.stem)
    section_dir = REPO_ROOT / args.section
    section_dir.mkdir(parents=True, exist_ok=True)
    dest_md = section_dir / f"{slug}.md"

    if dest_md.exists() and not args.force:
        print(f"error: {dest_md} already exists (use --force to overwrite)", file=sys.stderr)
        return 1

    vault_root = find_vault_root(source)
    img_dir = REPO_ROOT / "assets" / "img" / args.section / slug

    copied = []
    missing = []

    def replace_embed(m: re.Match) -> str:
        filename, alias = m.group(1).strip(), m.group(2)
        found = resolve_asset(filename, source, vault_root)
        if found is None:
            missing.append(filename)
            return m.group(0)
        dest_name = slugify(Path(filename).stem) + Path(filename).suffix.lower()
        img_dir.mkdir(parents=True, exist_ok=True)
        dest_path = img_dir / dest_name
        if not dest_path.exists() or args.force:
            shutil.copy2(found, dest_path)
        copied.append((found, dest_path))
        alt = (alias or Path(filename).stem).strip()
        return f"![{alt}](/assets/img/{args.section}/{slug}/{dest_name})"

    text = IMAGE_EMBED_RE.sub(replace_embed, text)

    leftover_links = [m.group(1) for m in WIKILINK_RE.finditer(text)]

    suspicious_lines = [
        (i, line) for i, line in enumerate(text.splitlines(), 1)
        if SUSPICIOUS_FENCE_RE.match(line)
    ]
    callouts = CALLOUT_RE.findall(text)

    parent_title = "Writeups" if args.section == "writeups" else "Notes"
    nav_order = compute_nav_order(section_dir, args.nav_order)

    front_matter = (
        "---\n"
        f"title: {title}\n"
        "layout: default\n"
        f"parent: {parent_title}\n"
        f"nav_order: {nav_order}\n"
        "---\n\n"
    )

    dest_md.write_text(front_matter + text.lstrip("\n"), encoding="utf-8")

    print(f"Wrote {dest_md.relative_to(REPO_ROOT)}")
    print(f"  title: {title}")
    print(f"  parent: {parent_title}, nav_order: {nav_order}")
    for src, dst in copied:
        print(f"  image: {src} -> {dst.relative_to(REPO_ROOT)}")
    if missing:
        print("\nWARNING: could not find these embedded files (left as [[...]] untouched):")
        for f in missing:
            print(f"  - {f}")
    if leftover_links:
        print("\nWARNING: plain [[wikilinks]] to other notes were left as-is (no Jekyll equivalent):")
        for link in leftover_links:
            print(f"  - {link}")
    if suspicious_lines:
        print("\nWARNING: lines that look like inline code using triple backticks")
        print("(this crashes the Rouge syntax highlighter -- use single backticks instead):")
        for lineno, line in suspicious_lines:
            print(f"  line {lineno}: {line.strip()}")
    if callouts:
        print("\nWARNING: Obsidian callout blocks found (> [!type] ...) -- Jekyll/kramdown")
        print("does not understand this syntax, it will render as a plain blockquote:")
        for kind in callouts:
            print(f"  - [!{kind}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
