"""
diagnose.py
Run this to find exactly what's causing the 404 error.

Usage:
    python diagnose.py
"""

import sys
import json
from pathlib import Path

print("\n" + "="*55)
print("  MR PIPELINE — DIAGNOSTICS")
print("="*55)

# ── CHECK 1: Config file ─────────────────────────────────────
print("\n[1] Checking config.py...")
try:
    from config import (GEMINI_API_KEY, GOOGLE_SHEET_ID,
                        SERVICE_ACCOUNT_JSON, WATCH_FOLDER)
    print(f"  WATCH_FOLDER       : {WATCH_FOLDER}")
    print(f"  GOOGLE_SHEET_ID    : {GOOGLE_SHEET_ID}")
    print(f"  SERVICE_ACCOUNT_JSON: {SERVICE_ACCOUNT_JSON}")
    print(f"  GEMINI_API_KEY     : {GEMINI_API_KEY[:8]}..." if len(GEMINI_API_KEY) > 8 else "  GEMINI_API_KEY: NOT SET")

    errors = []
    if "YOUR_GEMINI" in GEMINI_API_KEY:
        errors.append("  ✗ GEMINI_API_KEY is still the placeholder — replace it")
    if "YOUR_GOOGLE" in GOOGLE_SHEET_ID:
        errors.append("  ✗ GOOGLE_SHEET_ID is still the placeholder — replace it")
    if errors:
        for e in errors: print(e)
        print("\n  → Fix config.py and re-run diagnose.py")
        sys.exit(1)
    print("  ✓ Config values look non-empty")
except ImportError as e:
    print(f"  ✗ Cannot import config.py: {e}")
    sys.exit(1)

# ── CHECK 2: Credentials file exists ────────────────────────
print("\n[2] Checking service account JSON file...")
cred_path = Path(SERVICE_ACCOUNT_JSON)
if not cred_path.exists():
    print(f"  ✗ File NOT FOUND: {SERVICE_ACCOUNT_JSON}")
    print("  → Download it from Google Cloud Console → Service Accounts → Keys → JSON")
    sys.exit(1)

try:
    creds_data = json.loads(cred_path.read_text())
    sa_email = creds_data.get("client_email", "NOT FOUND")
    project  = creds_data.get("project_id", "NOT FOUND")
    print(f"  ✓ File found")
    print(f"  ✓ Service account email : {sa_email}")
    print(f"  ✓ Project ID            : {project}")
except Exception as e:
    print(f"  ✗ Cannot read JSON: {e}")
    sys.exit(1)

# ── CHECK 3: gspread auth ────────────────────────────────────
print("\n[3] Checking Google authentication...")
try:
    import gspread
    from google.oauth2.service_account import Credentials
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_JSON, scopes=SCOPES)
    client = gspread.authorize(creds)
    print("  ✓ Google auth successful")
except Exception as e:
    print(f"  ✗ Auth failed: {e}")
    sys.exit(1)

# ── CHECK 4: Can open the Sheet ──────────────────────────────
print("\n[4] Checking Google Sheet access...")
print(f"  Sheet ID: {GOOGLE_SHEET_ID}")
try:
    sheet = client.open_by_key(GOOGLE_SHEET_ID)
    print(f"  ✓ Sheet opened successfully: '{sheet.title}'")
    print(f"  ✓ Existing tabs: {[ws.title for ws in sheet.worksheets()]}")
except gspread.exceptions.APIError as e:
    status = e.response.status_code if hasattr(e, 'response') else "unknown"
    print(f"  ✗ API Error {status}: {e}")
    if "404" in str(e) or status == 404:
        print("""
  CAUSE: Sheet not found. Two possible reasons:

  A) Wrong Sheet ID in config.py
     → Open your Google Sheet in browser
     → Copy the ID from the URL:
       docs.google.com/spreadsheets/d/  <<<THIS PART>>>  /edit
     → Paste into config.py → GOOGLE_SHEET_ID

  B) Sheet not shared with service account
     → Open your Google Sheet
     → Click Share (top right)
     → Add this email as Editor:
""")
        print(f"       {sa_email}")
        print("""
     → Click Send
     → Re-run diagnose.py
""")
    elif "403" in str(e) or status == 403:
        print(f"""
  CAUSE: Permission denied.
  → Open your Google Sheet
  → Click Share → Add as Editor:
    {sa_email}
""")
    sys.exit(1)
except Exception as e:
    print(f"  ✗ Unexpected error: {e}")
    sys.exit(1)

# ── CHECK 5: Gemini API ──────────────────────────────────────
print("\n[5] Checking Gemini API...")
try:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
    resp = model.generate_content("Reply with just the word: OK")
    print(f"  ✓ Gemini Flash responded: {resp.text.strip()}")
except Exception as e:
    print(f"  ✗ Gemini error: {e}")
    print("  → Check your GEMINI_API_KEY at aistudio.google.com/app/apikey")
    sys.exit(1)

# ── CHECK 6: Inbox folder ────────────────────────────────────
print("\n[6] Checking watch folder...")
inbox = Path(WATCH_FOLDER) / "inbox"
if not inbox.exists():
    print(f"  ⚠ Inbox doesn't exist yet: {inbox}")
    print("  → It will be auto-created when you run main.py")
else:
    files = list(inbox.iterdir())
    print(f"  ✓ Inbox exists: {inbox}")
    print(f"  ✓ Files in inbox: {len(files)}")
    for f in files[:10]:
        print(f"    - {f.name}")

# ── ALL CLEAR ────────────────────────────────────────────────
print("\n" + "="*55)
print("  ALL CHECKS PASSED — pipeline is ready to run")
print("="*55)
print("\n  Next steps:")
print("  1. Drop files into inbox/")
print("  2. python main.py --test   (safe, no Sheets write)")
print("  3. python main.py --once   (live, writes to Sheets)")
print()
