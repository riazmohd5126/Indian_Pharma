# ============================================================
#  MR PIPELINE — CONFIGURATION
#  Fill in your keys before running
# ============================================================

# ── 1. GEMINI API KEY ────────────────────────────────────────
# Get free key at: https://aistudio.google.com/app/apikey
GEMINI_API_KEY = "AIzaSyCLbPUinUWQ1wN0l7Oq4EAGb_-WbGFtGkU"

# ── 2. LOCAL WATCH FOLDER ───────────────────────────────────
# Create this folder on your laptop. Drop photos + text files here.
# Windows example: r"C:\Users\Riaz\MR_Reports"
# Mac/Linux example: "/Users/riaz/MR_Reports"
WATCH_FOLDER = r"/Users/riazmohd/Downloads/mr_pipeline 2/MR_Reports"

# Sub-folders will be created automatically:
#   MR_Reports/
#     inbox/          ← MR drops files here
#     processed/      ← moved here after parsing
#     failed/         ← moved here if parsing fails

# ── 3. GOOGLE SHEETS ─────────────────────────────────────────
# Step 1: Create a Google Sheet and copy its ID from the URL
#   URL looks like: docs.google.com/spreadsheets/d/SHEET_ID/edit
GOOGLE_SHEET_ID = "1sT3rdkkLxrlEI2HCdusBTklKsWAcmSZYyZS6W-4wVGY"

# Sheet tab names (will be auto-created if missing)
SHEET_DAILY_REPORTS = "daily_reports"
SHEET_ORDERS        = "orders"
SHEET_EXCEPTIONS    = "exception_queue"

# Step 2: Download service account JSON from Google Cloud Console
#   https://console.cloud.google.com → IAM → Service Accounts
#   Enable: Google Sheets API + Google Drive API
#   Share your Google Sheet with the service account email
#   Share your "medicine sales" Drive folder with the service account email
SERVICE_ACCOUNT_JSON = r"/Users/riazmohd/Downloads/mr_pipeline 2/google_credentials.json"

# ── 5. GOOGLE DRIVE SOURCE FOLDER ───────────────────────────
# Top-level folder name in Google Drive where MR photos are stored.
# Structure expected:
#   medicine sales/
#     Tanzeem Ahmad/
#       20260309/          ← date folder (YYYYMMDD or DD-MM-YYYY)
#         photo1.jpg
#         photo2.jpg
DRIVE_ROOT_FOLDER_NAME = "medicine sales"

# ── 4. BUSINESS RULES ───────────────────────────────────────
# Your product master catalog — helps Gemini normalize names
PRODUCT_CATALOG = [
    "Acnerant Gel",
    "Aldiassur MR Tablet",
    "Aldiassur-P Tab",
    "Aldiassur-Plus Tab",
    "Aldiassur-SP",
    "Alkarant Syp",
    "Assurange Syp",
    "Assurant-GM Tub",
    "Assurant-OC Cream",
    "Assureshine Cream",
    "Assurgel Susp",
    "Calciasure Syrup",
    "Calciasure-D3 Tab",
    "Ciprorant-D Eye/Ear Drops",
    "Cloti Rant Dusting Powder",
    "Coughrant Cold Tab",
    "Coughrant Ex Syrup",
    "Coughrant Plus Susp",
    "Coughrant-DX Syp",
    "Coughrant-DX Tab",
    "Cyporant Syp",
    "Deflarant-6 Tab",
    "Diclorant Gel",
    "Diclorant Pain Oil",
    "Flucorant-150 Tab",
    "Flucorant-200 Tab",
    "Gentarant Ear Drop",
    "Gilow Asure Syrup",
    "Glimsure-PM2 Tab",
    "Hair Oil",
    "Heprant Tab",
    "Itarant-100",
    "Itarant-200",
    "Ketassur-2 Cream",
    "Ketorant Soap",
    "Kojirant Soap",
    "Lulirant Cream",
    "Lycorant Syrup",
    "Mefrant-D",
    "Neurasure Tablet",
    "Nimorant Tab",
    "Oflarant-200 Tab",
    "Oflarant-OZ Tab",
    "Oflasure-D Eye Drops",
    "Omiassure-D Cap",
    "Pantarant-40 Inj",
    "Pantarant-40 Tab",
    "Pantarant-DSR Capsule",
    "Parassur-250 Susp",
]

# Your MR team — maps WhatsApp sender names to MR records
MR_REGISTRY = {
    "Tanzeem Ahmad": {"hq": "Moradabad", "territory": ["Dalpatpur", "Karanpur"]},
    # Add more MRs here
}

# Confidence threshold — below this goes to exception queue
CONFIDENCE_THRESHOLD = 0.3

# ── 6. ALERTS (optional for later) ──────────────────────────
# EOD report expected by this hour (24h format)
EOD_DEADLINE_HOUR = 20  # 8 PM
