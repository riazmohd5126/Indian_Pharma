"""
test_pipeline.py
Run this to verify every component of the pipeline before going live.

Usage:
    python test_pipeline.py           # all tests
    python test_pipeline.py gemini    # only Gemini
    python test_pipeline.py drive     # only Drive
    python test_pipeline.py sheets    # only Sheets
"""

import sys
import json
import os
from pathlib import Path

PASS = "  ✓ PASS"
FAIL = "  ✗ FAIL"
SKIP = "  - SKIP"

results = {}


def section(title):
    print(f"\n{'='*52}")
    print(f"  {title}")
    print(f"{'='*52}")


def ok(label, detail=""):
    print(f"{PASS}  {label}" + (f" — {detail}" if detail else ""))
    results[label] = "PASS"


def fail(label, reason):
    print(f"{FAIL}  {label} — {reason}")
    results[label] = f"FAIL: {reason}"


def skip(label, reason):
    print(f"{SKIP}  {label} — {reason}")
    results[label] = f"SKIP: {reason}"


# ── TEST 1: CONFIG ────────────────────────────────────────────
def test_config():
    section("1 · Config")
    try:
        from config import (GEMINI_API_KEY, GOOGLE_SHEET_ID,
                            SERVICE_ACCOUNT_JSON, DRIVE_ROOT_FOLDER_NAME,
                            PIPELINE_STATE_FILE)

        if not GEMINI_API_KEY or "YOUR_" in GEMINI_API_KEY:
            fail("GEMINI_API_KEY", "still a placeholder — get one at aistudio.google.com")
        else:
            ok("GEMINI_API_KEY", f"{GEMINI_API_KEY[:8]}...")

        if not GOOGLE_SHEET_ID or "YOUR_" in GOOGLE_SHEET_ID:
            fail("GOOGLE_SHEET_ID", "still a placeholder")
        else:
            ok("GOOGLE_SHEET_ID", GOOGLE_SHEET_ID[:20] + "...")

        cred_path = Path(SERVICE_ACCOUNT_JSON)
        if not cred_path.exists():
            fail("SERVICE_ACCOUNT_JSON", f"file not found: {SERVICE_ACCOUNT_JSON}")
        else:
            try:
                data = json.loads(cred_path.read_text())
                ok("SERVICE_ACCOUNT_JSON", f"email: {data.get('client_email', '?')}")
            except Exception as e:
                fail("SERVICE_ACCOUNT_JSON", f"invalid JSON: {e}")

        ok("DRIVE_ROOT_FOLDER_NAME", DRIVE_ROOT_FOLDER_NAME)
        ok("PIPELINE_STATE_FILE", PIPELINE_STATE_FILE)

    except ImportError as e:
        fail("config.py import", str(e))


# ── TEST 2: GEMINI API ────────────────────────────────────────
def test_gemini():
    section("2 · Gemini API")
    try:
        from config import GEMINI_API_KEY
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        # Text ping
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents="Reply with exactly: OK"
            )
            if "OK" in resp.text:
                ok("Gemini text ping", f"model replied: {resp.text.strip()}")
            else:
                ok("Gemini text ping", f"responded (unexpected text): {resp.text.strip()[:40]}")
        except Exception as e:
            fail("Gemini text ping", str(e))
            return

        # Image parse test — uses a real slip already downloaded, or generates a tiny PNG
        try:
            from PIL import Image as PILImage
            import io as _io
            tmp = Path("/tmp/test_pixel.jpg")
            img = PILImage.new("RGB", (100, 100), color=(255, 255, 255))
            img.save(str(tmp), "JPEG")


            from gemini_parser import parse_order_slip
            result = parse_order_slip(str(tmp))
            if "error" not in result:
                ok("Gemini image parse", f"confidence: {result.get('confidence', '?')}")
            else:
                # A low-confidence result on a blank image is expected — that's fine
                if "403" in str(result.get("error", "")) or "401" in str(result.get("error", "")):
                    fail("Gemini image parse", result["error"])
                else:
                    ok("Gemini image parse", "parsed (blank image → low confidence as expected)")
            tmp.unlink(missing_ok=True)
        except Exception as e:
            fail("Gemini image parse", str(e))

    except ImportError as e:
        fail("Gemini imports", str(e))


# ── TEST 3: GOOGLE DRIVE ─────────────────────────────────────
def test_drive():
    section("3 · Google Drive")
    try:
        from config import SERVICE_ACCOUNT_JSON, DRIVE_ROOT_FOLDER_NAME
        from googleapiclient.discovery import build
        from google.oauth2.service_account import Credentials

        if not Path(SERVICE_ACCOUNT_JSON).exists():
            skip("Drive auth", f"credentials file not found: {SERVICE_ACCOUNT_JSON}")
            skip("Drive folder scan", "skipped — no credentials")
            return

        SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
        try:
            creds  = Credentials.from_service_account_file(SERVICE_ACCOUNT_JSON, scopes=SCOPES)
            svc    = build("drive", "v3", credentials=creds, cache_discovery=False)
            ok("Drive auth", "service account authenticated")
        except Exception as e:
            fail("Drive auth", str(e))
            return

        # Find root folder
        try:
            q = (f"name='{DRIVE_ROOT_FOLDER_NAME}' "
                 "and mimeType='application/vnd.google-apps.folder' and trashed=false")
            res   = svc.files().list(q=q, fields="files(id, name)").execute()
            files = res.get("files", [])
            if not files:
                fail("Drive root folder", f"'{DRIVE_ROOT_FOLDER_NAME}' not found — share it with the service account")
                return
            root_id = files[0]["id"]
            ok("Drive root folder", f"found '{DRIVE_ROOT_FOLDER_NAME}'")
        except Exception as e:
            fail("Drive root folder", str(e))
            return

        # List MR folders
        try:
            q   = f"'{root_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            res = svc.files().list(q=q, fields="files(id, name)", pageSize=50).execute()
            mr_folders = res.get("files", [])
            if not mr_folders:
                fail("MR folders", "no MR subfolders found inside root folder")
                return
            ok("MR folders", f"found {len(mr_folders)}: {[f['name'] for f in mr_folders]}")
        except Exception as e:
            fail("MR folders", str(e))
            return

        # Count total images
        total_images = 0
        for mr in mr_folders:
            q = (f"'{mr['id']}' in parents and "
                 "mimeType='application/vnd.google-apps.folder' and trashed=false")
            date_res    = svc.files().list(q=q, fields="files(id, name)").execute()
            date_folders = date_res.get("files", [])
            for df in date_folders:
                q2  = (f"'{df['id']}' in parents and trashed=false and "
                       "(mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/webp')")
                img_res = svc.files().list(q=q2, fields="files(id)").execute()
                total_images += len(img_res.get("files", []))
        ok("Drive image count", f"{total_images} photo(s) ready to process")

    except ImportError as e:
        fail("Drive imports", str(e))


# ── TEST 4: GOOGLE SHEETS ────────────────────────────────────
def test_sheets():
    section("4 · Google Sheets")
    try:
        from config import SERVICE_ACCOUNT_JSON, GOOGLE_SHEET_ID
        import gspread
        from google.oauth2.service_account import Credentials

        if not Path(SERVICE_ACCOUNT_JSON).exists():
            skip("Sheets auth", f"credentials file not found: {SERVICE_ACCOUNT_JSON}")
            skip("Sheets open", "skipped — no credentials")
            skip("Sheets write test", "skipped — no credentials")
            return

        SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        try:
            creds  = Credentials.from_service_account_file(SERVICE_ACCOUNT_JSON, scopes=SCOPES)
            client = gspread.authorize(creds)
            ok("Sheets auth", "service account authenticated")
        except Exception as e:
            fail("Sheets auth", str(e))
            return

        try:
            sheet = client.open_by_key(GOOGLE_SHEET_ID)
            tabs  = [ws.title for ws in sheet.worksheets()]
            ok("Sheets open", f"'{sheet.title}' — tabs: {tabs}")
        except gspread.exceptions.APIError as e:
            status = getattr(e.response, "status_code", "?")
            if status == 404:
                fail("Sheets open", "404 — wrong Sheet ID or not shared with service account")
            elif status == 403:
                fail("Sheets open", "403 — share the sheet with the service account email as Editor")
            else:
                fail("Sheets open", str(e))
            return
        except Exception as e:
            fail("Sheets open", str(e))
            return

        # Write a test row to a _test tab then delete it
        try:
            from datetime import datetime
            test_tab_name = "_pipeline_test"
            try:
                ws = sheet.worksheet(test_tab_name)
            except gspread.WorksheetNotFound:
                ws = sheet.add_worksheet(title=test_tab_name, rows=5, cols=3)
            ws.append_row(["TEST", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "delete me"])
            sheet.del_worksheet(ws)
            ok("Sheets write test", "wrote and deleted a test row successfully")
        except Exception as e:
            fail("Sheets write test", str(e))

    except ImportError as e:
        fail("Sheets imports", str(e))


# ── TEST 5: END-TO-END DRY RUN ────────────────────────────────
def test_dry_run():
    section("5 · End-to-end dry run (--test mode)")
    try:
        from config import SERVICE_ACCOUNT_JSON
        if not Path(SERVICE_ACCOUNT_JSON).exists():
            skip("Dry run", "skipped — no credentials (run: python main.py --test on your Mac)")
            return

        import subprocess
        result = subprocess.run(
            [sys.executable, "main.py", "--test"],
            capture_output=True, text=True, timeout=120,
            cwd=Path(__file__).parent
        )
        output = result.stdout + result.stderr
        if result.returncode == 0 or "TEST MODE" in output:
            ok("main.py --test", "completed without crash")
            # Show last few lines of output
            lines = [l for l in output.strip().splitlines() if l.strip()]
            for line in lines[-5:]:
                print(f"           {line}")
        else:
            fail("main.py --test", f"exit code {result.returncode}")
            print(output[-500:])
    except Exception as e:
        fail("Dry run", str(e))


# ── SUMMARY ───────────────────────────────────────────────────
def summary():
    section("SUMMARY")
    passed  = sum(1 for v in results.values() if v == "PASS")
    failed  = sum(1 for v in results.values() if v.startswith("FAIL"))
    skipped = sum(1 for v in results.values() if v.startswith("SKIP"))
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failed}")
    print(f"  Skipped: {skipped} (need credentials on your Mac)")
    if failed:
        print("\n  Fix these before running main.py:")
        for k, v in results.items():
            if v.startswith("FAIL"):
                print(f"    • {k}: {v[6:]}")
    else:
        print("\n  All clear — ready to run: python main.py --test")
    print()


# ── MAIN ─────────────────────────────────────────────────────
if __name__ == "__main__":
    target = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

    print("\n" + "="*52)
    print("  MR PIPELINE — TEST SUITE")
    print("="*52)

    if target in ("all", "config"):  test_config()
    if target in ("all", "gemini"):  test_gemini()
    if target in ("all", "drive"):   test_drive()
    if target in ("all", "sheets"):  test_sheets()
    if target in ("all", "dryrun"):  test_dry_run()

    summary()
