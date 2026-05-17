# MR Field Report Pipeline
### WhatsApp Photos + Text → Gemini AI → Google Sheets → Looker Studio

---

## WHAT THIS DOES

You drop MR order slip photos and EOD text reports into a folder on your laptop.
The pipeline automatically:
1. Reads and parses everything using Gemini Flash AI
2. Writes structured data into Google Sheets (3 tabs)
3. Your Looker Studio dashboard updates live

MRs do NOTHING different. You just collect their WhatsApp files and drop them in the folder.

---

## STEP 1 — Install Python Dependencies

```
pip install -r requirements.txt
```

---

## STEP 2 — Get Your Gemini API Key (Free)

1. Go to: https://aistudio.google.com/app/apikey
2. Sign in with Google
3. Click "Create API Key"
4. Copy the key into `config.py` → `GEMINI_API_KEY`

Free tier: **1,500 requests/day** (enough for your team)

---

## STEP 3 — Set Up Google Sheets

### A. Create the Sheet
1. Go to sheets.google.com
2. Create a new blank spreadsheet
3. Name it: "MR Pipeline Data"
4. Copy the Sheet ID from the URL:
   `docs.google.com/spreadsheets/d/THIS_IS_YOUR_ID/edit`
5. Paste into `config.py` → `GOOGLE_SHEET_ID`

### B. Create Service Account (one-time setup)
1. Go to: https://console.cloud.google.com
2. Create a new project (or use existing)
3. Search for "Google Sheets API" → Enable it
4. Search for "Google Drive API" → Enable it
5. Go to: IAM & Admin → Service Accounts
6. Click "Create Service Account"
   - Name: mr-pipeline
   - Click Create and Continue → Done
7. Click the service account email → Keys tab
8. Add Key → Create New Key → JSON
9. Download the JSON file
10. Save it as `google_credentials.json` inside your MR_Reports folder
11. Update `config.py` → `SERVICE_ACCOUNT_JSON` with the full path

### C. Share Your Sheet with Service Account
1. Open your Google Sheet
2. Click Share
3. Paste the service account email (looks like: mr-pipeline@yourproject.iam.gserviceaccount.com)
4. Give it Editor access
5. Click Send

---

## STEP 4 — Configure Your Settings

Open `config.py` and set:

```python
WATCH_FOLDER = r"C:\Users\YourName\MR_Reports"   # your folder path
GEMINI_API_KEY = "AIza..."                         # from Step 2
GOOGLE_SHEET_ID = "1BxiMVs0..."                   # from Step 3A
SERVICE_ACCOUNT_JSON = r"C:\Users\...\google_credentials.json"
```

Also add your products to `PRODUCT_CATALOG` — this helps Gemini normalize names.

---

## STEP 5 — Name Your Files

When you collect WhatsApp photos from MRs, rename them before dropping into inbox:

```
Format:  YYYYMMDD_MRFirstName_Type.ext

EOD report (text):   20260309_Tanzeem_EOD.txt
Slip photo 1:        20260309_Tanzeem_Slip1.jpg
Slip photo 2:        20260309_Tanzeem_Slip2.jpg
Slip photo 3:        20260309_Tanzeem_Slip3.jpg
```

Copy the MR's WhatsApp text message → paste into a .txt file → name it correctly.
Save the slip photos from WhatsApp → name them correctly.
Drop everything into: `MR_Reports/inbox/`

---

## STEP 6 — Run the Pipeline

### Test first (no Sheets write, just see output):
```
python main.py --test
```

### Process inbox once:
```
python main.py --once
```

### Watch folder continuously (checks every 30 seconds):
```
python main.py
```

---

## FOLDER STRUCTURE

```
MR_Reports/
  inbox/          ← Drop files here
  processed/      ← Auto-moved after successful parse
    20260309_Tanzeem/
      20260309_Tanzeem_EOD.txt
      20260309_Tanzeem_Slip1.jpg
  failed/         ← Auto-moved if parse fails
  pipeline.log    ← All activity logged here
  google_credentials.json
```

---

## GOOGLE SHEETS — 3 TABS AUTO-CREATED

### Tab 1: daily_reports
One row per MR per day. Columns:
Timestamp | MR Name | Date | HQ | Working Area | Working With |
TC | PC | POB (Rs) | Stockist | Slip Count | Remarks | Confidence | Status

### Tab 2: orders
One row per product ordered. Columns:
MR Name | Date | Customer | Customer Type | Area | Doctor |
Product (Raw) | Product (Normalized) | Quantity | Unit | Confidence | Linked EOD

### Tab 3: exception_queue
Low-confidence extractions needing review. Columns:
Type | MR Name | Date | Source File | Confidence | Issue | Raw Data | Status

---

## STEP 7 — Looker Studio Dashboard

1. Go to: https://lookerstudio.google.com
2. Create New Report
3. Add Data Source → Google Sheets → pick your "MR Pipeline Data" sheet
4. Build charts:

**Recommended charts:**
- Scorecard: Total POB Today (filter: date = today)
- Scorecard: Total TC / PC Today
- Bar chart: POB by MR Name (last 7 days)
- Line chart: Daily POB trend (last 30 days)
- Table: MR-wise TC vs PC with PC% calculated
- Table: Top products ordered this week
- Table: Exception queue count (needs attention)

---

## TROUBLESHOOTING

**"Permission denied" on Sheets**
→ Make sure you shared the Sheet with the service account email (Editor access)

**Gemini returns garbled JSON**
→ Check your GEMINI_API_KEY in config.py

**Files not being picked up**
→ Check file naming — must be YYYYMMDD_Name_EOD.txt or YYYYMMDD_Name_SlipN.jpg

**Low confidence on slips**
→ Ensure photos are well-lit and not blurry
→ The exception_queue tab will catch these for manual review

---

## NEXT PHASE (Later)

- MARG ERP sync via API or CSV export
- Automated WhatsApp alerts for missing reports
- Multi-MR batch processing from shared WhatsApp group
