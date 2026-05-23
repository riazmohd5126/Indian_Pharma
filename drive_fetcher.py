"""
drive_fetcher.py
Fetches WhatsApp order slip photos from Google Drive.

Expected Drive structure:
    MR_Pipeline_Input/
        Surendra/
            2026-05-07/      ← date folder (any format: YYYY-MM-DD, YYYYMMDD, DD-MM-YYYY)
                photo1.jpg
                photo2.jpg
            2026-05-08/
        Tanzeem Ahmad/
            2026-05-07/

Usage:
    from drive_fetcher import fetch_drive_groups
    groups = fetch_drive_groups()
    groups = fetch_drive_groups(target_date="20260507")
    groups = fetch_drive_groups(target_mr="Surendra")
"""

import re
import tempfile
from pathlib import Path
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials

from config import SERVICE_ACCOUNT_JSON, DRIVE_ROOT_FOLDER_NAME

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]

IMAGE_MIMES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp"
}


def _drive_service():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_JSON, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _find_folder(service, name: str, parent_id: str = None) -> dict | None:
    """Find a single folder by name, optionally scoped to a parent."""
    escaped = name.replace("'", "\\'")
    q = f"name='{escaped}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    res = service.files().list(q=q, fields="files(id, name)", pageSize=10).execute()
    files = res.get("files", [])
    return files[0] if files else None


def _list_folders(service, parent_id: str) -> list[dict]:
    """List all subfolders inside a folder."""
    q = (f"'{parent_id}' in parents"
         " and mimeType='application/vnd.google-apps.folder'"
         " and trashed=false")
    res = service.files().list(q=q, fields="files(id, name)", pageSize=200).execute()
    return res.get("files", [])


def _list_images(service, parent_id: str) -> list[dict]:
    """List all image files inside a folder."""
    mime_filter = " or ".join(f"mimeType='{m}'" for m in IMAGE_MIMES)
    q = f"'{parent_id}' in parents and trashed=false and ({mime_filter})"
    res = service.files().list(
        q=q, fields="files(id, name, mimeType)", pageSize=200
    ).execute()
    return res.get("files", [])


def _download(service, file_id: str, dest_path: str):
    """Download a Drive file to a local path."""
    request = service.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def _normalize_date(raw: str) -> str | None:
    """
    Convert various date folder names to YYYYMMDD.
    Handles: YYYYMMDD, DD-MM-YYYY, DD/MM/YYYY, YYYY-MM-DD
    Returns None if unparseable.
    """
    raw = raw.strip()
    formats = [
        ("%Y%m%d",    r"^\d{8}$"),
        ("%d-%m-%Y",  r"^\d{2}-\d{2}-\d{4}$"),
        ("%d/%m/%Y",  r"^\d{2}/\d{2}/\d{4}$"),
        ("%Y-%m-%d",  r"^\d{4}-\d{2}-\d{2}$"),
    ]
    for fmt, pattern in formats:
        if re.match(pattern, raw):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y%m%d")
            except ValueError:
                continue
    return None


def fetch_drive_groups(target_date: str = None, target_mr: str = None) -> dict:
    """
    Walk the Google Drive folder tree and download images into temp dirs.

    Args:
        target_date: optional YYYYMMDD to process only one date across all MRs.
        target_mr:   optional MR name (case-insensitive) to process only one MR.

    Returns:
        {
          "20260507_Surendra": {
              "key":        "20260507_Surendra",
              "eod":        None,
              "slips":      [Path(...), ...],
              "mr_name":    "Surendra",
              "date":       "20260507",
              "drive_path": "MR_Pipeline_Input/Surendra/2026-05-07",
          },
          ...
        }
    """
    service = _drive_service()

    root = _find_folder(service, DRIVE_ROOT_FOLDER_NAME)
    if not root:
        raise FileNotFoundError(
            f"Google Drive folder '{DRIVE_ROOT_FOLDER_NAME}' not found. "
            "Make sure it is shared with the service account."
        )

    groups = {}

    mr_folders = _list_folders(service, root["id"])
    if not mr_folders:
        print(f"  ⚠ No MR subfolders found inside '{DRIVE_ROOT_FOLDER_NAME}'")
        return groups

    for mr_folder in mr_folders:
        mr_name = mr_folder["name"].strip()

        if target_mr and target_mr.lower() not in mr_name.lower():
            continue

        mr_key_part = mr_name.split()[0] if mr_name else mr_name

        date_folders = _list_folders(service, mr_folder["id"])
        for date_folder in date_folders:
            raw_date      = date_folder["name"].strip()
            date_yyyymmdd = _normalize_date(raw_date)

            if not date_yyyymmdd:
                print(f"  ⚠ Skipping unrecognized date folder: {mr_name}/{raw_date}")
                continue

            if target_date and date_yyyymmdd != target_date:
                continue

            images = _list_images(service, date_folder["id"])
            if not images:
                continue

            tmp_dir    = Path(tempfile.mkdtemp(prefix=f"mr_{date_yyyymmdd}_{mr_key_part}_"))
            downloaded = []
            for img in images:
                dest = tmp_dir / img["name"]
                print(f"    ↓ {mr_name}/{raw_date}/{img['name']}")
                _download(service, img["id"], str(dest))
                downloaded.append(dest)

            if downloaded:
                key = f"{date_yyyymmdd}_{mr_key_part}"
                groups[key] = {
                    "key":        key,
                    "eod":        None,
                    "slips":      downloaded,
                    "mr_name":    mr_name,
                    "date":       date_yyyymmdd,
                    "drive_path": f"{DRIVE_ROOT_FOLDER_NAME}/{mr_name}/{raw_date}",
                }

    return groups
