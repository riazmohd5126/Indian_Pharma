"""
main.py
───────────────────────────────────────────────────
MR Field Report Pipeline — Main Entry Point

SOURCE: Google Drive → MR_Pipeline_Input/
  Structure:
    MR_Pipeline_Input/
      Surendra/
        2026-05-07/      ← upload photos here
          photo1.jpg
          photo2.jpg
        2026-05-08/
      Tanzeem Ahmad/
        2026-05-07/

HOW TO RUN:
  python main.py                      ← process all new Drive batches (default)
  python main.py --test               ← parse and print output, no Sheets write
  python main.py --date 20260507      ← process only this date across all MRs
  python main.py --mr Surendra        ← process only this MR (all dates)
  python main.py --reprocess          ← ignore processed log, redo everything
  python main.py --local              ← fallback: use local inbox/ folder instead
"""

import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

from config import WATCH_FOLDER, PIPELINE_STATE_FILE
from gemini_parser import parse_eod_report, parse_order_slip, link_slips_to_report
from sheets_writer import write_eod_report, write_order_slips, write_mr_tracking, write_mr_summary
from drive_fetcher import fetch_drive_groups

# ── PATHS ────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
STATE_FILE = SCRIPT_DIR / PIPELINE_STATE_FILE
LOG_FILE   = SCRIPT_DIR / "pipeline.log"

# Local inbox paths (--local mode only)
INBOX     = Path(WATCH_FOLDER) / "inbox"
PROCESSED = Path(WATCH_FOLDER) / "processed"
FAILED    = Path(WATCH_FOLDER) / "failed"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
TEXT_EXTS  = {".txt"}


# ── LOGGING ──────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── PROCESSED STATE ──────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def mark_done(state: dict, key: str, slips: int, drive_path: str):
    state[key] = {
        "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "slips":        slips,
        "status":       "done",
        "drive_path":   drive_path,
    }
    save_state(state)


def mark_error(state: dict, key: str, error: str, drive_path: str):
    state[key] = {
        "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status":       "error",
        "error":        error,
        "drive_path":   drive_path,
    }
    save_state(state)


# ── CORE PROCESSING ──────────────────────────────────────────

def process_group(group: dict, test_mode: bool = False, eod_override: dict = None):
    """Process one MR's slip photos for one day."""
    key        = group["key"]
    eod_file   = group.get("eod")
    slip_files = group["slips"]

    log(f"Processing: {key}  ({len(slip_files)} slip(s))")

    eod_data  = eod_override
    slip_data = []

    # Parse EOD text report if present (local mode)
    if eod_file:
        log(f"  Parsing EOD report: {eod_file.name}")
        text = eod_file.read_text(encoding="utf-8")
        eod_data = parse_eod_report(text)
        eod_data["source_file"] = eod_file.name
        if test_mode:
            print("\n── EOD PARSE RESULT ──")
            print(json.dumps(eod_data, indent=2))

    # Parse each order slip image
    for slip_f in slip_files:
        log(f"  Parsing slip: {slip_f.name}")
        result = parse_order_slip(str(slip_f))
        if test_mode:
            print(f"\n── SLIP: {slip_f.name} ──")
            print(json.dumps(result, indent=2))
        slip_data.append(result)

    # Link slips to EOD if available
    if eod_data and slip_data:
        eod_data     = link_slips_to_report(eod_data, slip_data)
        linked_slips = eod_data.get("matched_slips", []) + eod_data.get("unmatched_slips", [])
        unmatched    = eod_data.get("unmatched_slips", [])
        log(f"  Linked {len(linked_slips)} slip(s), {len(unmatched)} unmatched")
    else:
        linked_slips = slip_data

    # Write to Google Sheets
    if not test_mode:
        mr_name    = eod_data.get("mr_name", "") if eod_data else ""
        eod_date   = eod_data.get("date", "")    if eod_data else ""
        order_count = 0

        if eod_data:
            write_eod_report(eod_data, eod_file.name if eod_file else "")
        if linked_slips:
            order_count = write_order_slips(linked_slips, mr_name, eod_date)
        if eod_data:
            write_mr_tracking(eod_data, len(slip_files), order_count)
            write_mr_summary(eod_data, len(slip_files), order_count)
    else:
        log("  [TEST] Skipping Sheets write")

    # Move local files after processing (local mode only)
    if not test_mode and eod_file:
        dest = PROCESSED / key
        dest.mkdir(parents=True, exist_ok=True)
        for f in ([eod_file] if eod_file else []) + slip_files:
            shutil.move(str(f), str(dest / f.name))
            log(f"  Moved {f.name} → processed/{key}/")


# ── DRIVE MODE (default) ──────────────────────────────────────

def run_drive(test_mode: bool = False, target_date: str = None,
              target_mr: str = None, reprocess: bool = False):
    """Fetch from Google Drive and process all new MR/date batches."""

    state = {} if reprocess else load_state()

    log("Scanning Google Drive: MR_Pipeline_Input/")
    try:
        groups = fetch_drive_groups(target_date=target_date, target_mr=target_mr)
    except FileNotFoundError as e:
        log(f"ERROR: {e}")
        return

    if not groups:
        log("No photos found in Google Drive.")
        return

    new_groups = {k: v for k, v in groups.items()
                  if reprocess or state.get(k, {}).get("status") != "done"}

    skipped = len(groups) - len(new_groups)
    log(f"Found {len(groups)} batch(es) — {len(new_groups)} new, {skipped} already processed")

    if not new_groups:
        log("Nothing to do. Use --reprocess to force reprocessing.")
        return

    for key, group in new_groups.items():
        drive_path = group.get("drive_path", "")
        try:
            eod_stub = {
                "mr_name":       group.get("mr_name", ""),
                "date":          group.get("date", ""),
                "working_area":  [],
                "matched_slips": [],
                "confidence":    1.0,
            }
            process_group(group, test_mode=test_mode, eod_override=eod_stub)
            if not test_mode:
                mark_done(state, key, len(group["slips"]), drive_path)
                log(f"  ✓ {key} marked as done")
        except Exception as e:
            log(f"ERROR processing {key}: {e}")
            if not test_mode:
                mark_error(state, key, str(e), drive_path)


# ── LOCAL MODE (--local fallback) ────────────────────────────

def run_local(test_mode: bool = False):
    """Process files from the local inbox/ folder."""
    for folder in [INBOX, PROCESSED, FAILED]:
        folder.mkdir(parents=True, exist_ok=True)

    files = [f for f in INBOX.iterdir()
             if f.is_file() and f.suffix.lower() in IMAGE_EXTS | TEXT_EXTS]
    if not files:
        log("Local inbox is empty.")
        return

    log(f"Found {len(files)} file(s) in local inbox")
    groups = {}
    for f in files:
        parts = f.stem.split("_")
        if len(parts) < 2:
            log(f"  ⚠ Skipping (bad name): {f.name}")
            continue
        key = f"{parts[0]}_{parts[1]}"
        if key not in groups:
            groups[key] = {"key": key, "eod": None, "slips": []}
        name_upper = f.stem.upper()
        if f.suffix.lower() in TEXT_EXTS and "EOD" in name_upper:
            groups[key]["eod"] = f
        elif f.suffix.lower() in IMAGE_EXTS:
            groups[key]["slips"].append(f)

    for key, group in groups.items():
        try:
            process_group(group, test_mode=test_mode)
        except Exception as e:
            log(f"ERROR processing {key}: {e}")
            for f in ([group["eod"]] if group["eod"] else []) + group["slips"]:
                if f and f.exists():
                    shutil.move(str(f), str(FAILED / f.name))


# ── ENTRY POINT ──────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    test_mode  = "--test"       in args
    reprocess  = "--reprocess"  in args
    local_mode = "--local"      in args

    target_date = args[args.index("--date") + 1] if "--date" in args else None
    target_mr   = args[args.index("--mr")   + 1] if "--mr"   in args else None

    if test_mode:
        log("TEST MODE — Sheets write skipped, processed log not updated")

    if local_mode:
        log("LOCAL MODE — reading from local inbox/")
        run_local(test_mode=test_mode)
    else:
        run_drive(test_mode=test_mode, target_date=target_date,
                  target_mr=target_mr, reprocess=reprocess)

    log("Done.")
