"""
main.py
───────────────────────────────────────────────────
MR Field Report Pipeline — Main Entry Point

HOW IT WORKS (local inbox mode):
  1. Watches WATCH_FOLDER/inbox/ for new files
  2. Groups files by date prefix (e.g. 20260309_*)
  3. Parses text files as EOD reports
  4. Parses image files as order slips
  5. Links slips to EOD report
  6. Writes to Google Sheets
  7. Moves files to processed/ or failed/

HOW IT WORKS (--drive mode):
  1. Connects to Google Drive → "medicine sales" folder
  2. Walks MR subfolders → date subfolders → photos
  3. Downloads photos to a temp folder
  4. Parses as order slips and writes to Google Sheets

FILE NAMING CONVENTION FOR MRs (local mode):
  Text EOD reports:  YYYYMMDD_MRName_EOD.txt
                     e.g. 20260309_Tanzeem_EOD.txt
  Order slip images: YYYYMMDD_MRName_SlipN.jpg
                     e.g. 20260309_Tanzeem_Slip1.jpg

HOW TO RUN:
  python main.py                      ← watches local inbox continuously
  python main.py --once               ← process local inbox once and exit
  python main.py --test               ← parse local files, print output (no Sheets write)
  python main.py --drive              ← fetch from Google Drive and write to Sheets
  python main.py --drive --test       ← fetch from Drive, print output (no Sheets write)
  python main.py --drive --date 20260309  ← Drive fetch for a specific date only
"""

import os
import sys
import time
import shutil
import json
from pathlib import Path
from datetime import datetime

from config import WATCH_FOLDER
from gemini_parser import parse_eod_report, parse_order_slip, link_slips_to_report
from sheets_writer import write_eod_report, write_order_slips
from drive_fetcher import fetch_drive_groups

# ── FOLDER SETUP ─────────────────────────────────────────────
INBOX     = Path(WATCH_FOLDER) / "inbox"
PROCESSED = Path(WATCH_FOLDER) / "processed"
FAILED    = Path(WATCH_FOLDER) / "failed"
LOG_FILE  = Path(WATCH_FOLDER) / "pipeline.log"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
TEXT_EXTS  = {".txt"}


def setup_folders():
    for folder in [INBOX, PROCESSED, FAILED]:
        folder.mkdir(parents=True, exist_ok=True)
    print(f"""
╔══════════════════════════════════════════════════╗
║   MR PIPELINE — STARTED                         ║
╠══════════════════════════════════════════════════╣
║  Drop files into:                               ║
║  {str(INBOX):<44} ║
╠══════════════════════════════════════════════════╣
║  File naming:                                   ║
║  EOD text:  20260309_MRName_EOD.txt             ║
║  Slip photo: 20260309_MRName_Slip1.jpg          ║
╚══════════════════════════════════════════════════╝
""")


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def group_files_by_mr_date(files: list) -> dict:
    """
    Group inbox files by (date, mr_name) key.
    Returns: { "20260309_Tanzeem": {"eod": Path, "slips": [Path]} }
    """
    groups = {}
    for f in files:
        stem = f.stem  # e.g. 20260309_Tanzeem_EOD
        parts = stem.split("_")
        if len(parts) < 2:
            continue
        date_str = parts[0]
        mr_name  = parts[1]
        key = f"{date_str}_{mr_name}"

        if key not in groups:
            groups[key] = {"eod": None, "slips": [], "key": key}

        name_upper = stem.upper()
        if f.suffix.lower() in TEXT_EXTS and "EOD" in name_upper:
            groups[key]["eod"] = f
        elif f.suffix.lower() in IMAGE_EXTS:
            groups[key]["slips"].append(f)

    return groups


def process_group(group: dict, test_mode: bool = False, eod_override: dict = None):
    """Process one MR's files for one day.

    eod_override: pre-built eod stub used in Drive mode (no text file).
    """
    key       = group["key"]
    eod_file  = group["eod"]
    slip_files = group["slips"]

    log(f"Processing group: {key}  (EOD: {'yes' if eod_file else 'NO'}, Slips: {len(slip_files)})")

    eod_data  = eod_override  # may be None in local mode, pre-filled in Drive mode
    slip_data = []

    # ── Parse EOD report ─────────────────────────────────────
    if eod_file:
        log(f"  Parsing EOD report: {eod_file.name}")
        text = eod_file.read_text(encoding="utf-8")
        eod_data = parse_eod_report(text)
        eod_data["source_file"] = eod_file.name

        if test_mode:
            print("\n── EOD PARSE RESULT ──")
            print(json.dumps(eod_data, indent=2))

    # ── Parse order slips ─────────────────────────────────────
    for slip_f in slip_files:
        log(f"  Parsing slip image: {slip_f.name}")
        result = parse_order_slip(str(slip_f))

        if test_mode:
            print(f"\n── SLIP PARSE: {slip_f.name} ──")
            print(json.dumps(result, indent=2))

        slip_data.append(result)

    # ── Link slips to EOD ────────────────────────────────────
    if eod_data and slip_data:
        eod_data = link_slips_to_report(eod_data, slip_data)
        linked_slips = eod_data.get("matched_slips", []) + eod_data.get("unmatched_slips", [])
        unlinked     = eod_data.get("unmatched_slips", [])
        log(f"  Linked: {len(linked_slips)} slips matched, {len(unlinked)} unmatched")
    else:
        linked_slips = slip_data  # Write all slips regardless

    # ── Write to Sheets ──────────────────────────────────────
    if not test_mode:
        if eod_data:
            result = write_eod_report(eod_data, eod_file.name if eod_file else "")
        if linked_slips:
            mr_name  = eod_data.get("mr_name", "") if eod_data else ""
            eod_date = eod_data.get("date", "") if eod_data else ""
            write_order_slips(linked_slips, mr_name, eod_date)
    else:
        log("  [TEST MODE] Skipping Sheets write")

    # ── Move files to processed/ or failed/ ─────────────────
    if not test_mode:
        dest_folder = PROCESSED / key
        dest_folder.mkdir(parents=True, exist_ok=True)

        all_files = ([eod_file] if eod_file else []) + slip_files
        for f in all_files:
            shutil.move(str(f), str(dest_folder / f.name))
            log(f"  Moved {f.name} → processed/{key}/")


def process_inbox(test_mode: bool = False):
    """Scan inbox, group files, process each group."""
    files = [f for f in INBOX.iterdir()
             if f.is_file() and f.suffix.lower() in IMAGE_EXTS | TEXT_EXTS]

    if not files:
        return

    log(f"Found {len(files)} file(s) in inbox")
    groups = group_files_by_mr_date(files)

    if not groups:
        log("Could not group files — check naming convention")
        return

    for key, group in groups.items():
        try:
            process_group(group, test_mode=test_mode)
        except Exception as e:
            log(f"ERROR processing {key}: {e}")
            # Move to failed
            for f in ([group["eod"]] if group["eod"] else []) + group["slips"]:
                if f and f.exists():
                    shutil.move(str(f), str(FAILED / f.name))


def process_drive(test_mode: bool = False, target_date: str = None):
    """Fetch photos from Google Drive and process each MR/date group."""
    log(f"Fetching from Google Drive — folder: 'medicine sales'"
        + (f", date filter: {target_date}" if target_date else " (all dates)"))

    try:
        groups = fetch_drive_groups(target_date=target_date)
    except FileNotFoundError as e:
        log(f"ERROR: {e}")
        return

    if not groups:
        log("No files found in Google Drive for the given criteria.")
        return

    log(f"Found {len(groups)} group(s) in Drive")

    for key, group in groups.items():
        try:
            # Enrich eod_data stub from Drive metadata so write_order_slips has context
            drive_eod_stub = {
                "mr_name":      group.get("mr_name", ""),
                "date":         group.get("date", ""),
                "working_area": [],
                "matched_slips": [],
                "confidence":   1.0,
            }
            process_group(group, test_mode=test_mode, eod_override=drive_eod_stub)
        except Exception as e:
            log(f"ERROR processing {key}: {e}")


# ── ENTRY POINT ──────────────────────────────────────────────
if __name__ == "__main__":
    setup_folders()

    args = sys.argv[1:]
    test_mode   = "--test"  in args
    once_mode   = "--once"  in args
    drive_mode  = "--drive" in args

    # Optional: --date 20260309
    target_date = None
    if "--date" in args:
        idx = args.index("--date")
        if idx + 1 < len(args):
            target_date = args[idx + 1]

    if test_mode:
        log("Running in TEST MODE — no Sheets write, output printed to console")

    if drive_mode:
        log("Running in DRIVE MODE — fetching photos from Google Drive")
        process_drive(test_mode=test_mode, target_date=target_date)
        log("Done.")
    elif once_mode or test_mode:
        process_inbox(test_mode=test_mode)
        log("Done.")
    else:
        log("Watching local inbox... (Ctrl+C to stop)")
        while True:
            try:
                process_inbox()
                time.sleep(30)
            except KeyboardInterrupt:
                log("Stopped by user.")
                break
