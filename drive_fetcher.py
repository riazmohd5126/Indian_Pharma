"""
drive_fetcher.py
Fetches WhatsApp order slip photos from Google Drive.

Expected Drive structure:
    medicine sales/
        Tanzeem Ahmad/
            20260309/        ← date folder (YYYYMMDD or DD-MM-YYYY)
                img1.jpg
                img2.jpg
            20260310/
                ...

Usage:
    from drive_fetcher import fetch_drive_groups
    groups = fetch_drive_groups(target_date="20260309")
    # returns: { "20260309_Tanzeem": {"eod": None, "slips": ["/tmp/.../img.jpg"], "key": ...} }
"""

import io
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


def fetch_drive_groups(target_date: str = None) -> dict:
    """
    Walk the Google Drive folder tree and download images into temp dirs.

    Args:
        target_date: optional YYYYMMDD string to process only one date.
                     If None, fetches all dates.

    Returns dict in the same format that main.py's group_files_by_mr_date() produces:
        {
          "20260309_Tanzeem": {
              "key":   "20260309_Tanzeem",
              "eod":   None,           # Drive mode has no EOD text file
              "slips": [Path(...), ...]
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
        # Use the first word as the short key (matches YYYYMMDD_Tanzeem convention)
        mr_key_part = mr_name.split()[0] if mr_name else mr_name

        date_folders = _list_folders(service, mr_folder["id"])
        for date_folder in date_folders:
            raw_date  = date_folder["name"].strip()
            date_yyyymmdd = _normalize_date(raw_date)

            if not date_yyyymmdd:
                print(f"  ⚠ Skipping unrecognized date folder: {mr_name}/{raw_date}")
                continue

            if target_date and date_yyyymmdd != target_date:
                continue

            images = _list_images(service, date_folder["id"])
            if not images:
                continue

            # Download to a temp directory (cleaned up by OS on reboot)
            tmp_dir = Path(tempfile.mkdtemp(prefix=f"mr_{date_yyyymmdd}_{mr_key_part}_"))
            downloaded = []
            for img in images:
                ext  = Path(img["name"]).suffix.lower() or ".jpg"
                dest = tmp_dir / img["name"]
                print(f"    ↓ Downloading {mr_name}/{raw_date}/{img['name']}")
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
