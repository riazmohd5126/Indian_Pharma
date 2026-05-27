"""
sheets_writer.py
"""

import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import calendar
from config import (GOOGLE_SHEET_ID, SERVICE_ACCOUNT_JSON,
                    SHEET_DAILY_REPORTS, SHEET_ORDERS, SHEET_EXCEPTIONS,
                    SHEET_MR_TRACKING, SHEET_MR_SUMMARY,
                    CONFIDENCE_THRESHOLD)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

DAILY_HEADERS = [
    "Date", "MR Name", "HQ", "Working Area", "Working With",
    "Total Calls (TC)", "Productive Calls (PC)", "POB (Rs)",
    "Stockist", "Slip Count", "Remarks", "Confidence",
    "Source File", "Timestamp", "Status"
]

ORDER_HEADERS = [
    "Date", "MR Name", "Area", "Customer Name", "Customer Type",
    "Doctor Name", "Doctor Phone", "Reg Number",
    "Product (Raw)", "Product (Normalized)",
    "Quantity", "Unit", "Confidence",
    "Source File", "Linked EOD", "Timestamp"
]

EXCEPTION_HEADERS = [
    "Timestamp", "Type", "MR Name", "Date",
    "Source File", "Confidence", "Error/Issue",
    "Raw Data", "Status"
]

# Matches existing sheet structure
MR_SUMMARY_HEADERS = [
    "MR Name", "Month", "Monthly Target (Rs)", "POB Achieved (Rs)",
    "Achievement %", "Days Worked", "Working Days in Month", "Days Remaining",
    "Daily Avg POB", "Required Daily POB", "Projected Month End POB",
    "On Track?", "TC Total", "PC Total", "PC Rate %"
]

MR_TRACKING_HEADERS = [
    "MR Name", "Month", "Monthly Target (Rs)", "Total Working Days",
    "Working Days Elapsed", "Working Days Remaining", "Days MR Reported",
    "Days MR Absent (no report)", "POB Achieved (Rs)", "Achievement %",
    "Daily Avg POB (reported days)", "Required POB Per Day (remaining)",
    "Projected Month End (if avg continues)", "Projected Achievement %",
    "On Track?", "Shortfall / Surplus (Rs)", "TC Total", "PC Total", "PC Rate %"
]

MR_TARGETS_HEADERS = [
    "MR Name", "Monthly Target (Rs)", "Month", "Working Days"
]


def _get_sheet():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_JSON, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(GOOGLE_SHEET_ID)


def _ensure_tab(sheet, tab_name, headers):
    try:
        ws = sheet.worksheet(tab_name)
        existing = ws.row_values(1)
        if existing != headers:
            ws.delete_rows(1)
            ws.insert_row(headers, 1)
            ws.format("1:1", {
                "backgroundColor": {"red": 0.11, "green": 0.17, "blue": 0.29},
                "textFormat": {"bold": True,
                               "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER"
            })
            ws.freeze(rows=1)
            print(f"  ✓ Headers fixed: {tab_name}")
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=tab_name, rows=1000, cols=len(headers))
        ws.append_row(headers)
        ws.format("1:1", {
            "backgroundColor": {"red": 0.11, "green": 0.17, "blue": 0.29},
            "textFormat": {"bold": True,
                           "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER"
        })
        ws.freeze(rows=1)
        print(f"  ✓ Tab created: {tab_name}")
    return ws


def _to_int(v):
    try:
        return int(str(v).replace(",", "").replace("₹", "").strip())
    except Exception:
        return 0


def _working_days_in_month(year: int, month: int) -> int:
    """Count Mon–Sat days (6-day work week typical in Indian pharma)."""
    _, total = calendar.monthrange(year, month)
    count = 0
    for d in range(1, total + 1):
        if date(year, month, d).weekday() < 6:  # Mon=0 … Sat=5
            count += 1
    return count


def _working_days_elapsed(year: int, month: int) -> int:
    """Count Mon–Sat days from start of month up to today."""
    today = date.today()
    last_day = min(today.day, calendar.monthrange(year, month)[1])
    count = 0
    for d in range(1, last_day + 1):
        if date(year, month, d).weekday() < 6:
            count += 1
    return count


def _get_monthly_target(sheet, mr_name: str, month: str) -> int:
    """Look up monthly target from mr_targets tab. Returns 0 if not found."""
    try:
        ws = sheet.worksheet("mr_targets")
        rows = ws.get_all_values()
        for row in rows[1:]:
            if len(row) >= 2 and row[0].strip().lower() == mr_name.strip().lower():
                # row[2] = Month (may be YYYY-MM or empty for default)
                if len(row) < 3 or not row[2] or row[2] == month or row[2] == "":
                    return _to_int(row[1])
    except Exception:
        pass
    return 0


def write_eod_report(data: dict, source_file: str = "") -> str:
    confidence = data.get("confidence", 0.0)

    if confidence < CONFIDENCE_THRESHOLD or "error" in data:
        _write_exception(data, "eod_report", source_file, confidence)
        return "exception"

    sheet = _get_sheet()
    ws = _ensure_tab(sheet, SHEET_DAILY_REPORTS, DAILY_HEADERS)
    slip_count = len(data.get("matched_slips", []))
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row = [
        data.get("date", ""),
        data.get("mr_name", ""),
        data.get("hq", ""),
        ", ".join(data.get("working_area", [])),
        data.get("working_with", "self"),
        data.get("tc", 0),
        data.get("pc", 0),
        data.get("pob", 0),
        data.get("stockist", ""),
        slip_count,
        data.get("remarks", ""),
        round(confidence, 2),
        source_file,
        ts,
        "Auto-Approved"
    ]
    ws.append_row(row)
    print(f"  ✓ EOD report written — {data.get('mr_name')} | {data.get('date')}")
    return "written"


def write_order_slips(slips: list, eod_mr: str = "", eod_date: str = "") -> int:
    if not slips:
        return 0

    sheet = _get_sheet()
    ws = _ensure_tab(sheet, SHEET_ORDERS, ORDER_HEADERS)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_written = 0

    for slip in slips:
        confidence = slip.get("confidence", 0.0)
        if confidence < CONFIDENCE_THRESHOLD:
            _write_exception(slip, "order_slip", slip.get("source_file", ""), confidence)
            continue

        orders = slip.get("orders", [])
        if not orders:
            orders = [{"product_raw": "", "product_normalized": "",
                       "quantity": 0, "unit": ""}]

        for order in orders:
            row = [
                slip.get("date", eod_date),
                eod_mr or slip.get("linked_mr", ""),
                slip.get("area", ""),
                slip.get("customer_name", ""),
                slip.get("customer_type", ""),
                slip.get("doctor_name", ""),
                slip.get("doctor_phone", ""),
                slip.get("reg_number", ""),
                order.get("product_raw", ""),
                order.get("product_normalized", ""),
                order.get("quantity", 0),
                order.get("unit", ""),
                round(confidence, 2),
                slip.get("source_file", ""),
                f"{eod_mr} | {eod_date}" if eod_mr else "",
                ts
            ]
            ws.append_row(row)
            rows_written += 1

    print(f"  ✓ {rows_written} order line(s) written to sheets")
    return rows_written


def write_mr_tracking(eod_data: dict, slip_count: int, order_count: int):
    """Upsert monthly MR tracking row with actuals vs targets and projections."""
    sheet = _get_sheet()
    ws = _ensure_tab(sheet, SHEET_MR_TRACKING, MR_TRACKING_HEADERS)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    mr_name  = eod_data.get("mr_name", "")
    date_str = eod_data.get("date", "")
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        month = dt.strftime("%Y-%m")
        year, mon = dt.year, dt.month
    except Exception:
        month = date_str[:7] if len(date_str) >= 7 else date_str
        year, mon = int(month[:4]), int(month[5:7])

    monthly_target    = _get_monthly_target(sheet, mr_name, month)
    total_work_days   = _working_days_in_month(year, mon)
    elapsed_days      = _working_days_elapsed(year, mon)
    remaining_days    = max(total_work_days - elapsed_days, 0)

    # Read existing row to accumulate totals
    all_rows = ws.get_all_values()
    existing_row_idx = None
    for i, row in enumerate(all_rows[1:], start=2):
        if len(row) >= 2 and row[0].strip() == mr_name and row[1].strip() == month:
            existing_row_idx = i
            break

    if existing_row_idx:
        er = all_rows[existing_row_idx - 1]
        days_reported = _to_int(er[6]) + 1
        pob_achieved  = _to_int(er[8])  + (eod_data.get("pob") or 0)
        tc_total      = _to_int(er[16]) + (eod_data.get("tc") or 0)
        pc_total      = _to_int(er[17]) + (eod_data.get("pc") or 0)
    else:
        days_reported = 1
        pob_achieved  = eod_data.get("pob") or 0
        tc_total      = eod_data.get("tc") or 0
        pc_total      = eod_data.get("pc") or 0

    days_absent       = max(elapsed_days - days_reported, 0)
    achievement_pct   = round(pob_achieved / monthly_target * 100, 1) if monthly_target else 0
    daily_avg         = round(pob_achieved / days_reported, 0) if days_reported else 0
    req_per_day       = round((monthly_target - pob_achieved) / remaining_days, 0) if remaining_days else 0
    projected_end     = round(pob_achieved + daily_avg * remaining_days, 0)
    proj_ach_pct      = round(projected_end / monthly_target * 100, 1) if monthly_target else 0
    on_track          = "Yes" if projected_end >= monthly_target else "No"
    shortfall_surplus = projected_end - monthly_target
    pc_rate           = round(pc_total / tc_total * 100, 1) if tc_total else 0

    new_row = [
        mr_name, month, monthly_target, total_work_days,
        elapsed_days, remaining_days, days_reported, days_absent,
        pob_achieved, achievement_pct, daily_avg, req_per_day,
        projected_end, proj_ach_pct, on_track, shortfall_surplus,
        tc_total, pc_total, pc_rate
    ]

    if existing_row_idx:
        ws.update(f"A{existing_row_idx}:S{existing_row_idx}", [new_row])
        print(f"  ✓ MR tracking updated — {mr_name} | {month}")
    else:
        ws.append_row(new_row)
        print(f"  ✓ MR tracking created — {mr_name} | {month}")


def write_mr_summary(eod_data: dict, slip_count: int, order_count: int):
    """Upsert monthly summary row per MR with achievement vs target."""
    sheet = _get_sheet()
    ws = _ensure_tab(sheet, SHEET_MR_SUMMARY, MR_SUMMARY_HEADERS)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    mr_name  = eod_data.get("mr_name", "")
    date_str = eod_data.get("date", "")
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        month = dt.strftime("%Y-%m")
        year, mon = dt.year, dt.month
    except Exception:
        month = date_str[:7] if len(date_str) >= 7 else date_str
        year, mon = int(month[:4]), int(month[5:7])

    monthly_target  = _get_monthly_target(sheet, mr_name, month)
    total_work_days = _working_days_in_month(year, mon)
    elapsed_days    = _working_days_elapsed(year, mon)
    remaining_days  = max(total_work_days - elapsed_days, 0)

    all_rows = ws.get_all_values()
    existing_row_idx = None
    for i, row in enumerate(all_rows[1:], start=2):
        if len(row) >= 2 and row[0].strip() == mr_name and row[1].strip() == month:
            existing_row_idx = i
            break

    if existing_row_idx:
        er = all_rows[existing_row_idx - 1]
        days_worked  = _to_int(er[5]) + 1
        pob_achieved = _to_int(er[3]) + (eod_data.get("pob") or 0)
        tc_total     = _to_int(er[12]) + (eod_data.get("tc") or 0)
        pc_total     = _to_int(er[13]) + (eod_data.get("pc") or 0)
    else:
        days_worked  = 1
        pob_achieved = eod_data.get("pob") or 0
        tc_total     = eod_data.get("tc") or 0
        pc_total     = eod_data.get("pc") or 0

    achievement_pct   = round(pob_achieved / monthly_target * 100, 1) if monthly_target else 0
    daily_avg         = round(pob_achieved / days_worked, 0) if days_worked else 0
    req_daily         = round((monthly_target - pob_achieved) / remaining_days, 0) if remaining_days else 0
    projected_end     = round(pob_achieved + daily_avg * remaining_days, 0)
    on_track          = "Yes" if projected_end >= monthly_target else "No"
    pc_rate           = round(pc_total / tc_total * 100, 1) if tc_total else 0

    new_row = [
        mr_name, month, monthly_target, pob_achieved,
        achievement_pct, days_worked, total_work_days, remaining_days,
        daily_avg, req_daily, projected_end,
        on_track, tc_total, pc_total, pc_rate
    ]

    if existing_row_idx:
        ws.update(f"A{existing_row_idx}:O{existing_row_idx}", [new_row])
        print(f"  ✓ MR summary updated — {mr_name} | {month}")
    else:
        ws.append_row(new_row)
        print(f"  ✓ MR summary created — {mr_name} | {month}")


def _write_exception(data: dict, data_type: str, source_file: str, confidence: float):
    sheet = _get_sheet()
    ws = _ensure_tab(sheet, SHEET_EXCEPTIONS, EXCEPTION_HEADERS)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [
        ts, data_type,
        data.get("mr_name", "") or data.get("customer_name", ""),
        data.get("date", ""),
        source_file,
        round(confidence, 2),
        data.get("error", f"Low confidence: {confidence}"),
        json.dumps(data)[:500],
        "Needs Review"
    ]
    ws.append_row(row)
    print(f"  ⚠ Exception logged — {source_file} (confidence: {confidence})")
