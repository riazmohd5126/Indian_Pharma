"""
gemini_parser.py  (UPDATED — uses google-genai SDK + gemini-2.0-flash)
"""

import json
import base64
import re
from pathlib import Path
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, PRODUCT_CATALOG

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL  = "gemini-2.0-flash"

CATALOG_STR = "\n".join(f"  - {p}" for p in PRODUCT_CATALOG)

SYSTEM_CONTEXT = f"""You are a data extraction assistant for an Indian pharmaceutical distribution company.
You extract structured data from Medical Representative (MR) field reports.

Product catalog for normalization:
{CATALOG_STR}

Always match product names to the closest catalog entry.
Return ONLY valid JSON. No markdown, no explanation, no extra text."""

EOD_PROMPT = """Extract all fields from this MR end-of-day WhatsApp report.

Report text:
{text}

Return this exact JSON structure:
{{
  "type": "eod_report",
  "mr_name": "",
  "date": "YYYY-MM-DD",
  "hq": "",
  "working_area": [],
  "working_with": "",
  "tc": 0,
  "pc": 0,
  "pob": 0,
  "stockist": "",
  "remarks": "",
  "confidence": 0.0,
  "raw_text": ""
}}

Rules:
- date: convert any date format to YYYY-MM-DD
- working_area: list of area names mentioned
- tc: Total Calls (integer)
- pc: Productive Calls (integer)
- pob: Pharma Order Booking value in rupees (integer, strip Rs and commas)
- confidence: 0.0 to 1.0
- raw_text: copy the original text exactly"""

SLIP_PROMPT = """This is a photo of a handwritten pharmaceutical order slip (Dorset estimate pad).
Extract all information visible on the slip.

Return this exact JSON structure:
{{
  "type": "order_slip",
  "customer_name": "",
  "customer_type": "pharmacy|clinic|doctor|unknown",
  "area": "",
  "date": "YYYY-MM-DD",
  "doctor_name": "",
  "doctor_phone": "",
  "reg_number": "",
  "orders": [
    {{
      "product_raw": "",
      "product_normalized": "",
      "quantity": 0,
      "unit": "pcs|box|strip|bottle|unknown"
    }}
  ],
  "confidence": 0.0,
  "notes": ""
}}

Rules:
- product_normalized: match to closest catalog product name
- unit: pcs for pieces/packs, box for boxes
- If date not visible use today date
- confidence: 0.0 to 1.0
- notes: any additional text visible on the slip"""


def parse_eod_report(text: str) -> dict:
    prompt = SYSTEM_CONTEXT + "\n\n" + EOD_PROMPT.format(text=text)
    try:
        response = client.models.generate_content(model=MODEL, contents=prompt)
        raw = re.sub(r"```json|```", "", response.text.strip()).strip()
        data = json.loads(raw)
        data["parse_type"] = "eod_report"
        return data
    except Exception as e:
        print(f"  ERROR parsing EOD: {e}")
        return {"parse_type": "eod_report", "error": str(e), "confidence": 0.0, "raw_text": text}


def parse_order_slip(image_path: str) -> dict:
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        ext = Path(image_path).suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".webp": "image/webp"}
        mime_type = mime_map.get(ext, "image/jpeg")
        full_prompt = SYSTEM_CONTEXT + "\n\n" + SLIP_PROMPT
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_text(text=full_prompt),
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ]
        )
        raw = re.sub(r"```json|```", "", response.text.strip()).strip()
        data = json.loads(raw)
        data["parse_type"] = "order_slip"
        data["source_file"] = Path(image_path).name
        return data
    except Exception as e:
        print(f"  ERROR parsing slip {Path(image_path).name}: {e}")
        return {"parse_type": "order_slip", "error": str(e),
                "confidence": 0.0, "source_file": Path(image_path).name}


def link_slips_to_report(eod_report: dict, order_slips: list) -> dict:
    mr_name   = eod_report.get("mr_name", "")
    eod_date  = eod_report.get("date", "")
    eod_areas = [(a or "").lower() for a in eod_report.get("working_area", [])]
    matched, unmatched = [], []
    for slip in order_slips:
        slip_area  = (slip.get("area") or "").lower()
        slip_date  = slip.get("date", "")
        area_match = any(a in slip_area or slip_area in a for a in eod_areas)
        date_match = slip_date == eod_date or not slip_date
        if area_match or date_match:
            slip["linked_mr"] = mr_name
            matched.append(slip)
        else:
            unmatched.append(slip)
    eod_report["matched_slips"]   = matched
    eod_report["unmatched_slips"] = unmatched
    return eod_report
