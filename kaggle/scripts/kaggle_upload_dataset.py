#!/usr/bin/env python3
"""
kaggle_upload_dataset.py — Upload local file as private Kaggle dataset.

Usage:
    python3 scripts/kaggle_upload_dataset.py \
        --file /path/to/data.csv \
        --title "My Dataset Title" \
        --username adamschlesien \
        --token KGAT_ace4cd1d3f2180478e5d9a064d448f40

Prints the dataset slug on success (e.g. adamschlesien/my-dataset-title).
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(title: str) -> str:
    """Convert title to Kaggle-compatible slug (lowercase, hyphens)."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:50]  # Kaggle max slug length


def bearer_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# ── Step 1: Get blob upload token ─────────────────────────────────────────────

def get_blob_token(filepath: Path, token: str) -> tuple[str, str]:
    """Request a GCS resumable upload URL from Kaggle blob API."""
    stat = filepath.stat()
    payload = {
        "type": "DATASET",           # Required — without this: HTTP 400
        "name": filepath.name,
        "contentLength": stat.st_size,
        "lastModifiedEpochSeconds": int(stat.st_mtime),
    }
    r = requests.post(
        "https://www.kaggle.com/api/v1/blobs/upload",
        headers=bearer_headers(token),
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data["token"], data["createUrl"]


# ── Step 2: Upload file to GCS ────────────────────────────────────────────────

def upload_to_gcs(filepath: Path, create_url: str) -> None:
    """Upload file bytes to GCS resumable upload URL."""
    size = filepath.stat().st_size
    print(f"  Uploading {filepath.name} ({size/1024:.0f} KB) to GCS...", flush=True)

    with open(filepath, "rb") as f:
        data = f.read()

    r = requests.put(
        create_url,
        headers={"Content-Type": "application/octet-stream"},
        data=data,
        timeout=300,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"GCS upload failed: HTTP {r.status_code}\n{r.text[:500]}")
    print("  GCS upload OK.", flush=True)


# ── Step 3: Create dataset ────────────────────────────────────────────────────

def create_dataset(
    blob_token: str,
    title: str,
    username: str,
    api_token: str,
    is_private: bool = True,
) -> str:
    """Create a new Kaggle dataset referencing the uploaded blob. Returns slug."""
    payload = {
        "title": title,
        "ownerSlug": username,
        "isPrivate": is_private,
        "licenseName": "CC0-1.0",
        "files": [{"token": blob_token}],
    }
    r = requests.post(
        "https://www.kaggle.com/api/v1/datasets/create/new",
        headers=bearer_headers(api_token),
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()

    if data.get("status") == "Ok" or not data.get("error"):
        slug = slugify(title)
        return f"{username}/{slug}"
    else:
        raise RuntimeError(f"Dataset creation failed: {data.get('error', data)}")


# ── Step 4: Add new version to existing dataset ───────────────────────────────

def add_dataset_version(
    blob_token: str,
    username: str,
    slug: str,
    api_token: str,
    notes: str = "Updated",
) -> None:
    """Add a new version to an existing dataset."""
    payload = {
        "versionNotes": notes,
        "files": [{"token": blob_token}],
        "deleteSources": False,
    }
    r = requests.post(
        f"https://www.kaggle.com/api/v1/datasets/{username}/{slug}/versions",
        headers=bearer_headers(api_token),
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") not in ("Ok", None) and data.get("error"):
        raise RuntimeError(f"Version add failed: {data.get('error', data)}")
    print(f"  New version added to {username}/{slug}", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Upload file as private Kaggle dataset")
    p.add_argument("--file", required=True, help="Path to local file to upload")
    p.add_argument("--title", required=True, help="Dataset title (6-50 chars)")
    p.add_argument("--username", default="adamschlesien", help="Kaggle username")
    p.add_argument("--token", default=os.environ.get("KAGGLE_API_TOKEN"), help="KGAT_ API token")
    p.add_argument("--public", action="store_true", help="Make dataset public (default: private)")
    p.add_argument("--update", action="store_true", help="Add new version if dataset already exists")
    p.add_argument("--version-notes", default="Updated", help="Notes for new version (with --update)")
    args = p.parse_args()

    if not args.token:
        print("ERROR: Provide --token or set KAGGLE_API_TOKEN env var", file=sys.stderr)
        sys.exit(1)

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"ERROR: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    slug = slugify(args.title)
    full_ref = f"{args.username}/{slug}"

    print(f"Kaggle Dataset Upload")
    print(f"  File:    {filepath} ({filepath.stat().st_size/1024:.0f} KB)")
    print(f"  Dataset: {full_ref}")
    print(f"  Private: {not args.public}")
    print()

    # Step 1
    print("[1/3] Getting blob upload token...")
    blob_token, create_url = get_blob_token(filepath, args.token)
    print(f"  Token: {blob_token[:40]}...")

    # Step 2
    print("[2/3] Uploading to GCS...")
    upload_to_gcs(filepath, create_url)

    # Step 3
    print("[3/3] Creating/updating dataset on Kaggle...")
    if args.update:
        add_dataset_version(blob_token, args.username, slug, args.token, args.version_notes)
    else:
        result = create_dataset(blob_token, args.title, args.username, args.token, not args.public)
        print(f"  Dataset created: {result}")

    print()
    print(f"Done! Dataset: https://www.kaggle.com/datasets/{full_ref}")
    print(f"Slug for notebook: {full_ref}")
    print(f"Input path in notebook: /kaggle/input/{slug}/<filename>")


if __name__ == "__main__":
    main()
