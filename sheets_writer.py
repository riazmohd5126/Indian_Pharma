"""
sheets_writer.py
"""

import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
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

MR_TRACKING_HEADERS = [
    "Date", "MR Name", "HQ", "Working Area", "Working With",
    "TC", "PC", "POB (Rs)", "Km Travelled", "Stockist",
    "Slips Filed", "Orders Booked", "Timestamp"
]

MR_SUMMARY_HEADERS = [
    "MR Name", "Month", "Total TC", "Total PC", "Total POB (Rs)",
    "Working Days", "Total Slips", "Total Orders", "Last Updated"
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


def write_eod_report(data: dict, source_file: str = "") -> str:
    confidence = data.get("confidence", 0.0)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if confidence < CONFIDENCE_THRESHOLD or "error" in data:
        _write_exception(data, "eod_report", source_file, confidence)
        return "exception"

    sheet = _get_sheet()
    ws = _ensure_tab(sheet, SHEET_DAILY_REPORTS, DAILY_HEADERS)
    slip_count = len(data.get("matched_slips", []))

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
    """Write one daily activity row per MR to the mr_tracking tab."""
    sheet = _get_sheet()
    ws = _ensure_tab(sheet, SHEET_MR_TRACKING, MR_TRACKING_HEADERS)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row = [
        eod_data.get("date", ""),
        eod_data.get("mr_name", ""),
        eod_data.get("hq", ""),
        ", ".join(eod_data.get("working_area", [])),
        eod_data.get("working_with", "Self"),
        eod_data.get("tc", 0),
        eod_data.get("pc", 0),
        eod_data.get("pob", 0),
        eod_data.get("km_travelled", ""),
        eod_data.get("stockist", ""),
        slip_count,
        order_count,
        ts,
    ]
    ws.append_row(row)
    print(f"  ✓ MR tracking written — {eod_data.get('mr_name')} | {eod_data.get('date')}")


def write_mr_summary(eod_data: dict, slip_count: int, order_count: int):
    """Upsert monthly summary row per MR in the mr_summary tab."""
    sheet = _get_sheet()
    ws = _ensure_tab(sheet, SHEET_MR_SUMMARY, MR_SUMMARY_HEADERS)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    mr_name = eod_data.get("mr_name", "")
    date_str = eod_data.get("date", "")
    try:
        month = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m")
    except Exception:
        month = date_str[:7] if len(date_str) >= 7 else date_str

    # Find existing row for this MR + month to update it
    all_rows = ws.get_all_values()
    target_row_idx = None
    for i, row in enumerate(all_rows[1:], start=2):  # skip header
        if len(row) >= 2 and row[0] == mr_name and row[1] == month:
            target_row_idx = i
            break

    if target_row_idx:
        existing = all_rows[target_row_idx - 1]
        def _int(v):
            try: return int(str(v).replace(",", ""))
            except: return 0
        new_row = [
            mr_name, month,
            _int(existing[2]) + (eod_data.get("tc") or 0),
            _int(existing[3]) + (eod_data.get("pc") or 0),
            _int(existing[4]) + (eod_data.get("pob") or 0),
            _int(existing[5]) + 1,
            _int(existing[6]) + slip_count,
            _int(existing[7]) + order_count,
            ts,
        ]
        ws.update(f"A{target_row_idx}:I{target_row_idx}", [new_row])
        print(f"  ✓ MR summary updated — {mr_name} | {month}")
    else:
        row = [
            mr_name, month,
            eod_data.get("tc", 0),
            eod_data.get("pc", 0),
            eod_data.get("pob", 0),
            1,
            slip_count,
            order_count,
            ts,
        ]
        ws.append_row(row)
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
