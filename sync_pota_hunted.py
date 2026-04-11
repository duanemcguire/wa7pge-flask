#!/usr/bin/env python3
"""
Sync POTA hunted contacts from rigbook.db into pages/POTA/Hunted/.

For each contact with a pota_park value:
  - If a page for that park already exists, append the contact to the Hunter Log.
  - If no page exists, create one using data from the POTA API.

Safe to run repeatedly — existing log entries are not duplicated.
"""

import sqlite3
import os
import re
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

RIGBOOK_DB = os.path.expanduser("~/.local/rigbook/rigbook.db")
PAGES_DIR = Path(__file__).parent / "pages" / "POTA" / "Hunted"
POTA_API = "https://api.pota.app/park/{}"

# Seconds between API calls to be polite
API_DELAY = 0.5

# Cache park API responses within a single run
_park_cache = {}


def freq_to_band(freq_str):
    """Convert a frequency string to a band label like '20M'.

    rigbook stores frequencies in kHz (e.g. 14032.5), but some entries are
    in Hz (e.g. 14032000). Normalize to MHz before lookup.
    """
    if not freq_str:
        return "?M"
    try:
        freq = float(freq_str)
    except ValueError:
        return "?M"
    # Normalize to MHz
    if freq > 100_000:
        freq /= 1_000_000  # Hz → MHz
    elif freq > 100:
        freq /= 1_000      # kHz → MHz

    bands = [
        (1.8, 2.0, "160M"),
        (3.5, 4.0, "80M"),
        (5.3, 5.4, "60M"),
        (7.0, 7.3, "40M"),
        (10.1, 10.15, "30M"),
        (14.0, 14.35, "20M"),
        (18.068, 18.168, "17M"),
        (21.0, 21.45, "15M"),
        (24.89, 24.99, "12M"),
        (28.0, 29.7, "10M"),
        (50.0, 54.0, "6M"),
        (144.0, 148.0, "2M"),
    ]
    for low, high, label in bands:
        if low <= freq < high:
            return label
    return "?M"


def fetch_park(reference):
    """Fetch park metadata from the POTA API. Returns dict or None."""
    if reference in _park_cache:
        return _park_cache[reference]
    url = POTA_API.format(reference)
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        _park_cache[reference] = data
        time.sleep(API_DELAY)
        return data
    except Exception as e:
        print(f"  WARNING: could not fetch {url}: {e}")
        _park_cache[reference] = None
        return None


def find_existing_page(reference):
    """
    Find a page for a given park reference by scanning Hunted subdirectories.
    Returns Path or None.
    """
    for path in PAGES_DIR.rglob(f"{reference} *.md"):
        return path
    return None


def log_entry_exists(page_path, date_str, callsign):
    """Return True if a log line with this date and callsign already exists."""
    content = page_path.read_text(encoding="utf-8")
    # Match lines like: 2024-09-18 [W4LOO](...)
    pattern = re.compile(
        r"^\s*" + re.escape(date_str) + r"\s+\[" + re.escape(callsign) + r"\]",
        re.MULTILINE,
    )
    return bool(pattern.search(content))


def make_log_line(date_str, callsign, band, mode):
    return f"{date_str} [{callsign}](https://qrz.com/db/{callsign}) {band} {mode}"


def append_to_log(page_path, log_line):
    """Append a log line to the Hunter Log section, creating the section if absent."""
    content = page_path.read_text(encoding="utf-8")

    # Look for an existing Hunter Log heading (flexible: ##, ####, etc.)
    if re.search(r"^#{1,6}\s+My Hunter Log", content, re.MULTILINE):
        # Append after the last existing log entry (end of file, or before next heading)
        content = content.rstrip() + "\n" + log_line + "\n"
    else:
        content = content.rstrip() + "\n\n## My Hunter Log\n" + log_line + "\n"

    page_path.write_text(content, encoding="utf-8")


def create_page(park, state_dir, reference, callsign, band, mode, date_str):
    """Create a new park page with frontmatter and the first log entry."""
    name = park.get("name", reference)
    parktype = park.get("parktypeDesc", "")
    full_name = f"{name} {parktype}".strip()
    website = park.get("website") or ""
    location_name = park.get("locationName", "Unknown")

    # Use locationName as the directory (matches existing convention)
    target_dir = PAGES_DIR / location_name
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{reference} {full_name}.md"
    page_path = target_dir / filename

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    log_line = make_log_line(date_str, callsign, band, mode)

    spc = park.get("locationDesc", "").split("-")[-1].lower()

    lines = [
        "---",
        f"date: '{now}'",
        f"title: {reference} {full_name}",
        f"spc: {spc}",
        "---",
        "",
    ]
    if website:
        lines += [website, ""]
    lines += [
        "## My Hunter Log",
        log_line,
        "",
    ]

    page_path.write_text("\n".join(lines), encoding="utf-8")
    return page_path


def expand_contacts(rows):
    """
    Expand rows with multiple parks (e.g. 'US-0819,US-0647') into one row per park.
    Skips non-POTA references like SOTA summits.
    """
    expanded = []
    for row in rows:
        raw = row["pota_park"].strip()
        for ref in raw.split(","):
            ref = ref.strip()
            # Skip non-POTA references (SOTA, etc.) — valid refs match XX-NNNNN
            if not re.match(r"^[A-Z]{2}-\d+$", ref):
                continue
            expanded.append((ref, row))
    return expanded


def get_pota_contacts(db_path):
    """Return all contacts with a non-empty pota_park, oldest first."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT id, call, freq, mode, pota_park, timestamp
        FROM contacts
        WHERE pota_park IS NOT NULL AND pota_park != ''
        ORDER BY timestamp
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN — no files will be written\n")

    raw_contacts = get_pota_contacts(RIGBOOK_DB)
    contacts = expand_contacts(raw_contacts)
    print(f"Found {len(raw_contacts)} POTA contacts ({len(contacts)} park references) in rigbook.db")

    new_pages = 0
    new_entries = 0
    skipped = 0

    for reference, row in contacts:
        callsign = row["call"].strip().upper()
        freq = row["freq"] or ""
        mode = (row["mode"] or "").upper()
        ts = row["timestamp"]
        date_str = ts[:10]  # YYYY-MM-DD
        band = freq_to_band(freq)

        existing = find_existing_page(reference)

        if existing:
            if log_entry_exists(existing, date_str, callsign):
                skipped += 1
                continue
            park = fetch_park(reference)
            if park is None:
                print(f"  SKIP {reference} — API unavailable")
                continue
            log_line = make_log_line(date_str, callsign, band, mode)
            if not dry_run:
                append_to_log(existing, log_line)
            print(f"  {'WOULD APPEND' if dry_run else 'APPENDED'} {reference}: {log_line}")
            new_entries += 1
        else:
            park = fetch_park(reference)
            if park is None:
                print(f"  SKIP {reference} — API unavailable, cannot create page")
                continue
            if not dry_run:
                page_path = create_page(park, PAGES_DIR, reference, callsign, band, mode, date_str)
                print(f"  CREATED  {page_path.relative_to(Path(__file__).parent)}")
            else:
                name = park.get("name", reference)
                parktype = park.get("parktypeDesc", "")
                location_name = park.get("locationName", "Unknown")
                print(f"  WOULD CREATE {location_name}/{reference} {name} {parktype}.md")
            new_pages += 1

    verb = "would be" if dry_run else "were"
    print(
        f"\nDone. {new_pages} pages {verb} created, {new_entries} entries {verb} added, {skipped} already present."
    )


if __name__ == "__main__":
    main()
