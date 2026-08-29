"""
Vercel Blob storage helper.

Talks to Vercel Blob's HTTP API directly (no third-party SDK — the
official SDK is JS-only, and the community Python wrapper is unofficial
and thin enough that hitting the REST endpoint ourselves is simpler to
own long-term).

Requires BLOB_READ_WRITE_TOKEN in the environment. This works the same
way in local dev and in production on Vercel — same token, same host,
no local emulation needed.

Docs: https://vercel.com/docs/vercel-blob
"""

from __future__ import annotations

import os
import re
import unicodedata

import httpx
from fastapi import UploadFile

BLOB_API_BASE = "https://blob.vercel-storage.com"
BLOB_API_VERSION = "10"  # sent as x-api-version, matches current @vercel/blob SDK

MAX_UPLOAD_BYTES = 4 * 1024 * 1024  # stay safely under Vercel's 4.5MB function body cap

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


class BlobStorageError(Exception):
    """Raised when a Vercel Blob API call fails or is misconfigured."""


def _get_token() -> str:
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise BlobStorageError(
            "BLOB_READ_WRITE_TOKEN is not set. Create a Blob store in the "
            "Vercel dashboard (Storage tab) and connect it to this project."
        )
    return token


def _slugify_filename(filename: str) -> str:
    """Make a filename safe for use as a URL path segment."""
    name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode()
    name = name.strip().lower().replace(" ", "-")
    name = re.sub(r"[^a-z0-9._-]", "", name)
    return name or "file"


async def upload_image(file: UploadFile, category: str) -> dict:
    """
    Upload a single image to Vercel Blob under products/{category}/{filename}.

    Returns the blob API's response dict, e.g.:
        {
            "url": "https://<store>.public.blob.vercel-storage.com/products/panel/foo-AbC123.jpg",
            "pathname": "products/panel/foo-AbC123.jpg",
            "contentType": "image/jpeg",
            "contentDisposition": "attachment; filename=\"foo.jpg\"",
            "downloadUrl": "...",
        }

    Raises BlobStorageError on any failure (bad token, oversized file,
    disallowed content type, network/API error).
    """
    token = _get_token()

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise BlobStorageError(
            f"Unsupported image type {content_type!r}. "
            f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
        )

    body = await file.read()
    if len(body) > MAX_UPLOAD_BYTES:
        raise BlobStorageError(
            f"Image too large ({len(body) / 1024 / 1024:.1f}MB). "
            f"Max is {MAX_UPLOAD_BYTES / 1024 / 1024:.0f}MB per image."
        )
    if not body:
        raise BlobStorageError("Uploaded file is empty.")

    safe_category = _slugify_filename(category or "misc")
    safe_filename = _slugify_filename(file.filename or "image")
    pathname = f"products/{safe_category}/{safe_filename}"

    headers = {
        "access": "public",
        "authorization": f"Bearer {token}",
        "x-api-version": BLOB_API_VERSION,
        "x-content-type": content_type,
        # Random suffix avoids collisions when two admins upload
        # "panel.jpg" for different products.
        "x-add-random-suffix": "1",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.put(
                f"{BLOB_API_BASE}/",
                params={"pathname": pathname},
                headers=headers,
                content=body,
            )
        except httpx.HTTPError as e:
            raise BlobStorageError(f"Could not reach Vercel Blob: {e}") from e

    if response.status_code >= 400:
        raise BlobStorageError(
            f"Vercel Blob upload failed ({response.status_code}): {response.text}"
        )

    return response.json()


async def delete_images(urls: list[str]) -> None:
    """
    Delete one or more images from Vercel Blob by their full URLs.

    Silently no-ops on an empty list. Raises BlobStorageError if the
    delete call itself fails (a 404 for an already-missing blob is not
    treated as fatal, since the end state — "gone" — is what we want).
    """
    if not urls:
        return

    token = _get_token()
    headers = {
        "authorization": f"Bearer {token}",
        "x-api-version": BLOB_API_VERSION,
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{BLOB_API_BASE}/delete",
                headers=headers,
                json={"urls": urls},
            )
        except httpx.HTTPError as e:
            raise BlobStorageError(f"Could not reach Vercel Blob: {e}") from e

    if response.status_code >= 400 and response.status_code != 404:
        raise BlobStorageError(
            f"Vercel Blob delete failed ({response.status_code}): {response.text}"
        )
