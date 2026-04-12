#!/usr/bin/env python3
"""
Walk static/work/, find corresponding POTA/Hunted pages, and inject image
tags into pages that don't yet have any images.

Image naming convention in static/work/:
  {reference}map.{ext}   — map image (e.g. US-1048map.png)
  {reference}.{ext}      — primary photo (e.g. US-1048.png)
  {reference}[a-z].{ext} — additional photos (e.g. US-1048b.png)

Images are moved from static/work/ to static/ and referenced as /static/FILENAME.
Map image is inserted first, then photo(s) in alphabetical order.
Images are placed after the pota.app link (if present), or before the Hunter Log.
"""

import re
import sys
import shutil
from pathlib import Path
from collections import defaultdict

BASE_DIR   = Path(__file__).parent
WORK_DIR   = BASE_DIR / "static" / "work"
STATIC_DIR = BASE_DIR / "static"
PAGES_DIR  = BASE_DIR / "pages" / "POTA" / "Hunted"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Matches e.g. US-1048, US-11027, CA-3128
REF_RE = re.compile(r"^([A-Z]{2}-\d+)(map|[a-z]?)$", re.IGNORECASE)


def parse_work_images():
    """
    Return a dict keyed by park reference, value is a dict with:
      'map':    Path or None
      'photos': list of Paths (sorted)
    """
    groups = defaultdict(lambda: {"map": None, "photos": []})

    for f in sorted(WORK_DIR.iterdir()):
        if f.suffix.lower() not in IMAGE_EXTS:
            continue
        stem = f.stem  # e.g. "US-1048map" or "US-1048" or "US-1048b"
        m = REF_RE.match(stem)
        if not m:
            print(f"  SKIP unrecognised filename: {f.name}")
            continue
        ref    = m.group(1).upper()
        suffix = m.group(2).lower()  # "map", "", "b", "c", …
        if suffix == "map":
            groups[ref]["map"] = f
        else:
            groups[ref]["photos"].append(f)

    # Sort photos within each group
    for ref in groups:
        groups[ref]["photos"].sort()

    return groups


def find_page(reference):
    """Return the Path of the .md file for this reference, or None."""
    for p in PAGES_DIR.rglob(f"{reference} *.md"):
        return p
    return None


def page_has_images(content):
    """Return True if the page body (after frontmatter) already has an image tag."""
    # Strip frontmatter
    body = re.sub(r"^---\n.*?\n---\n", "", content, count=1, flags=re.DOTALL)
    return "![" in body


def build_img_tags(map_file, photo_files):
    """Build a list of markdown image tag lines."""
    tags = []
    if map_file:
        tags.append(f"![](/static/{map_file.name})")
    for f in photo_files:
        tags.append(f"![](/static/{f.name})")
    return tags


def inject_images(page_path, img_tags, dry_run):
    """Insert image tags into the page after the pota.app link, or before the Hunter Log."""
    content = page_path.read_text(encoding="utf-8")
    lines   = content.splitlines(keepends=True)

    # Find insertion point: after pota.app link line, or before Hunter Log heading
    insert_after = None   # index of line after which to insert
    hunter_log   = None   # index of Hunter Log heading line

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and "pota.app" in stripped:
            insert_after = i
        if re.match(r"^#{1,6}\s+My Hunter Log", stripped):
            hunter_log = i
            break

    if insert_after is not None:
        pos = insert_after + 1
    elif hunter_log is not None:
        pos = hunter_log
    else:
        pos = len(lines)

    # Build block: blank line + images + blank line
    # Ensure exactly one blank line before and after the image block
    block = ["\n"] + [tag + "\n" for tag in img_tags] + ["\n"]

    # If the line immediately before pos is already blank, no need for our leading blank
    if pos > 0 and lines[pos - 1].strip() == "":
        block = block[1:]

    # If the line at pos is already blank, no need for our trailing blank
    if pos < len(lines) and lines[pos].strip() == "":
        block = block[:-1]

    new_lines = lines[:pos] + block + lines[pos:]
    new_content = "".join(new_lines)

    if not dry_run:
        page_path.write_text(new_content, encoding="utf-8")

    return new_content


def move_image(src, dry_run):
    """Move a file from static/work/ to static/."""
    dest = STATIC_DIR / src.name
    if dest.exists():
        print(f"    already in static/: {src.name} (skipping move)")
        return dest
    if not dry_run:
        shutil.move(str(src), str(dest))
    return dest


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN — no files will be changed\n")

    groups = parse_work_images()
    if not groups:
        print("No images found in static/work/")
        return

    print(f"Found images for {len(groups)} park(s) in static/work/\n")

    injected = 0
    skipped  = 0

    for ref, files in sorted(groups.items()):
        map_file    = files["map"]
        photo_files = files["photos"]
        all_files   = ([map_file] if map_file else []) + photo_files

        page = find_page(ref)
        if page is None:
            print(f"  {ref}: no page found — skipping")
            skipped += 1
            continue

        content = page.read_text(encoding="utf-8")
        if page_has_images(content):
            print(f"  {ref}: page already has images — skipping")
            skipped += 1
            continue

        img_tags = build_img_tags(map_file, photo_files)
        inject_images(page, img_tags, dry_run)

        action = "WOULD INJECT" if dry_run else "INJECTED"
        print(f"  {ref}: {action} into {page.relative_to(BASE_DIR)}")
        for tag in img_tags:
            print(f"    {tag}")

        # Move images to static/
        for f in all_files:
            moved = move_image(f, dry_run)
            verb = "WOULD MOVE" if dry_run else "MOVED"
            print(f"    {verb} {f.name} → static/")

        injected += 1

    verb = "would be" if dry_run else "were"
    print(f"\nDone. {injected} page(s) {verb} updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
