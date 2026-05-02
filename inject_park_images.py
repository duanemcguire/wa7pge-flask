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
WORK_DIR   = Path("/home/duane/Pictures/Screenshots/")
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


def find_text_file(reference):
    """Return Path to {reference}.txt in WORK_DIR if it exists, else None."""
    candidate = WORK_DIR / (reference + ".txt")
    return candidate if candidate.exists() else None


INJECTED_DIV_ID = "injected_by_script"


def inject_text_block(page_path, text_content, dry_run):
    """Insert or replace a <div id="injected_by_script"> before the Hunter Log heading."""
    content = page_path.read_text(encoding="utf-8")
    div_open = f'<div id="{INJECTED_DIV_ID}" style="margin-bottom: 10px;">'
    inner = text_content.strip()
    new_block = f"{div_open}\n{inner}\n</div>"

    if div_open in content:
        # Replace existing block in-place
        new_content = re.sub(
            re.escape(div_open) + r".*?</div>",
            new_block,
            content,
            count=1,
            flags=re.DOTALL,
        )
    else:
        lines = content.splitlines(keepends=True)
        hunter_log = None
        for i, line in enumerate(lines):
            if re.match(r"^#{1,6}\s+My Hunter Log", line.strip()):
                hunter_log = i
                break

        pos = hunter_log if hunter_log is not None else len(lines)

        block_lines = (new_block + "\n\n").splitlines(keepends=True)
        if pos > 0 and lines[pos - 1].strip() != "":
            block_lines = ["\n"] + block_lines

        new_lines = lines[:pos] + block_lines + lines[pos:]
        new_content = "".join(new_lines)

    if not dry_run:
        page_path.write_text(new_content, encoding="utf-8")

    return new_content


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

    # Also include parks that have only a .txt file in WORK_DIR
    for f in sorted(WORK_DIR.iterdir()):
        if f.suffix == ".txt":
            m = re.match(r"^([A-Z]{2}-\d+)$", f.stem, re.IGNORECASE)
            if m:
                ref = m.group(1).upper()
                if ref not in groups:
                    groups[ref] = {"map": None, "photos": []}

    if not groups:
        print("Nothing to process in WORK_DIR.")
        return

    print(f"Found work for {len(groups)} park(s)\n")

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
        did_something = False

        if not all_files:
            pass  # txt-only park, no images to inject
        elif page_has_images(content):
            print(f"  {ref}: page already has images — skipping image injection")
        else:
            img_tags = build_img_tags(map_file, photo_files)
            inject_images(page, img_tags, dry_run)

            action = "WOULD INJECT" if dry_run else "INJECTED"
            print(f"  {ref}: {action} images into {page.relative_to(BASE_DIR)}")
            for tag in img_tags:
                print(f"    {tag}")

            # Move images to static/
            for f in all_files:
                move_image(f, dry_run)
                verb = "WOULD MOVE" if dry_run else "MOVED"
                print(f"    {verb} {f.name} → static/")

            did_something = True

        txt_file = find_text_file(ref)
        if txt_file:
            text_content = txt_file.read_text(encoding="utf-8")
            inject_text_block(page, text_content, dry_run)
            action = "WOULD INJECT" if dry_run else "INJECTED"
            print(f"  {ref}: {action} text block from {txt_file.name}")
            did_something = True

        if did_something:
            injected += 1
        else:
            skipped += 1

    verb = "would be" if dry_run else "were"
    print(f"\nDone. {injected} page(s) {verb} updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
