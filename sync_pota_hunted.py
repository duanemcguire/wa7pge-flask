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
    """Convert a frequency string to a band label like '20m'.

    rigbook stores frequencies in kHz (e.g. 14032.5), but some entries are
    in Hz (e.g. 14032000). Normalize to MHz before lookup.
    """
    if not freq_str:
        return "?m"
    try:
        freq = float(freq_str)
    except ValueError:
        return "?m"
    # Normalize to MHz
    if freq > 100_000:
        freq /= 1_000_000  # Hz → MHz
    elif freq > 100:
        freq /= 1_000      # kHz → MHz

    bands = [
        (1.8, 2.0, "160m"),
        (3.5, 4.0, "80m"),
        (5.3, 5.4, "60m"),
        (7.0, 7.3, "40m"),
        (10.1, 10.15, "30m"),
        (14.0, 14.35, "20m"),
        (18.068, 18.168, "17m"),
        (21.0, 21.45, "15m"),
        (24.89, 24.99, "12m"),
        (28.0, 29.7, "10m"),
        (50.0, 54.0, "6m"),
        (144.0, 148.0, "2m"),
    ]
    for low, high, label in bands:
        if low <= freq < high:
            return label
    return "?m"


def freq_to_mhz(freq_str):
    """Convert a frequency string to a display string in MHz (e.g. '14.065')."""
    if not freq_str:
        return ""
    try:
        freq = float(freq_str)
    except ValueError:
        return freq_str
    if freq > 100_000:
        freq /= 1_000_000  # Hz → MHz
    elif freq > 100:
        freq /= 1_000      # kHz → MHz
    # Format with up to 4 decimal places, strip trailing zeros
    return f"{freq:.4f}".rstrip("0").rstrip(".")


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
    for line in content.splitlines():
        if date_str in line and f"[{callsign}]" in line:
            return True
    return False


def make_log_line(time_str, date_str, callsign, rst_sent, rst_recv, state, freq_str, band, mode, reference):
    """Build a formatted log line with <BR> prefix for proper markdown rendering."""
    freq_mhz = freq_to_mhz(freq_str)
    pota_url = f"https://pota.app/#/park/{reference}"
    qrz_url = f"https://qrz.com/db/{callsign}"
    parts = [
        time_str,
        date_str,
        f"[{callsign}]({qrz_url})",
        rst_sent or "599",
        rst_recv or "599",
        state or "",
        freq_mhz,
        band,
        mode,
        f"[{reference}]({pota_url})",
    ]
    return "<BR>" + "\t".join(parts)


def get_state_from_rigbook(reference, db_path):
    """
    For multi-jurisdictional parks, look up the unique state from rigbook.db.
    Returns a 2-letter state abbreviation if unique, else None.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        """
        SELECT DISTINCT state FROM contacts
        WHERE (pota_park = ? OR pota_park LIKE ? OR pota_park LIKE ? OR pota_park LIKE ?)
          AND state IS NOT NULL AND state != ''
        """,
        (reference, f"{reference},%", f"%,{reference}", f"%,{reference},%"),
    )
    states = [row[0].upper() for row in cur.fetchall() if row[0]]
    conn.close()
    unique = list(set(states))
    if len(unique) == 1:
        return unique[0]
    return None


def is_multi_jurisdictional(loc_desc):
    """Return True if locationDesc indicates multiple states (e.g. 'US-VA,US-WV')."""
    return "," in loc_desc


def get_spc_and_location(park, reference, db_path):
    """
    Determine the 2-letter state code (spc) and location name for a park.
    For multi-jurisdictional parks, looks up rigbook.db for a unique state.
    """
    loc_desc = park.get("locationDesc", "")
    location_name = park.get("locationName", "Unknown")

    if is_multi_jurisdictional(loc_desc) or is_multi_jurisdictional(location_name):
        unique_state = get_state_from_rigbook(reference, db_path)
        if unique_state:
            spc = unique_state.upper()
            # Use the first part of locationName if it's also multi-valued
            if "," in location_name:
                location_name = location_name.split(",")[0].strip()
            return spc, location_name

    spc = loc_desc.split("-")[-1].upper()
    return spc, location_name



def append_to_log(page_path, log_line):
    """Append a log line to the Hunter Log section, creating the section if absent."""
    content = page_path.read_text(encoding="utf-8")

    # Look for an existing Hunter Log heading (flexible: ##, ####, etc.)
    if re.search(r"^#{1,6}\s+My Hunter Log", content, re.MULTILINE):
        content = content.rstrip() + "\n" + log_line + "\n"
    else:
        content = content.rstrip() + "\n\n#### My Hunter Log\n" + log_line + "\n"

    page_path.write_text(content, encoding="utf-8")


def create_page(park, reference, callsign, band, mode, date_str, time_str,
                rst_sent, rst_recv, state, freq, db_path, dry_run=False):
    """Create a new park page with frontmatter and the first log entry."""
    name = park.get("name", reference)
    parktype = park.get("parktypeDesc", "")
    full_name = f"{name} {parktype}".strip()

    spc, location_name = get_spc_and_location(park, reference, db_path)

    target_dir = PAGES_DIR / location_name
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{reference} {full_name}.md"
    page_path = target_dir / filename

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_line = make_log_line(time_str, date_str, callsign, rst_sent, rst_recv, state, freq, band, mode, reference)

    pota_link = f"[{reference}](https://pota.app/#/park/{reference})"

    lines = [
        "---",
        f"date: '{today}'",
        f"title: {reference} {full_name}",
        f"spc: {spc}",
        "---",
        "",
        pota_link,
        "",
        "#### My Hunter Log",
        log_line,
        "",
    ]

    if not dry_run:
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
        SELECT id, call, freq, mode, rst_sent, rst_recv, state, pota_park, timestamp
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
        rst_sent = row["rst_sent"] or "599"
        rst_recv = row["rst_recv"] or "599"
        state = (row["state"] or "").upper()
        ts = row["timestamp"]
        date_str = ts[:10]          # YYYY-MM-DD
        time_str = ts[11:16]        # HH:MM
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
            log_line = make_log_line(time_str, date_str, callsign, rst_sent, rst_recv, state, freq, band, mode, reference)
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
                page_path = create_page(
                    park, reference, callsign, band, mode, date_str, time_str,
                    rst_sent, rst_recv, state, freq, RIGBOOK_DB,
                )
                print(f"  CREATED  {page_path.relative_to(Path(__file__).parent)}")
            else:
                name = park.get("name", reference)
                parktype = park.get("parktypeDesc", "")
                spc, location_name = get_spc_and_location(park, reference, RIGBOOK_DB)
                print(f"  WOULD CREATE {location_name}/{reference} {name} {parktype}.md  (spc={spc})")
            new_pages += 1

    verb = "would be" if dry_run else "were"
    print(
        f"\nDone. {new_pages} pages {verb} created, {new_entries} entries {verb} added, {skipped} already present."
    )


if __name__ == "__main__":
    main()
