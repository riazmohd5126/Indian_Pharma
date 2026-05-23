"""
sheets_writer.py  — clean rewrite with proper column order
"""

import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from config import (GOOGLE_SHEET_ID, SERVICE_ACCOUNT_JSON,
                    SHEET_DAILY_REPORTS, SHEET_ORDERS,
                    SHEET_EXCEPTIONS, CONFIDENCE_THRESHOLD)

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
