import logging
import re
import base64
from typing import Optional

import httpx

from .config import settings, DEFAULT_HEADERS

logger = logging.getLogger(__name__)

QWEN_BASE = settings.qwen_base_url

_upload_client: Optional[httpx.AsyncClient] = None


def _get_upload_client() -> httpx.AsyncClient:
    global _upload_client
    if _upload_client is None:
        _upload_client = httpx.AsyncClient(timeout=120.0)
    return _upload_client


async def upload_file(token: str, file_path: str, file_type: str = "document") -> Optional[str]:
    url = f"{QWEN_BASE}/api/v2/files/upload"
    headers = {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {token}",
    }
    client = _get_upload_client()
    with open(file_path, "rb") as f:
        files = {"file": f}
        resp = await client.post(url, headers=headers, files=files)
    if resp.status_code != 200:
        logger.error(f"Upload failed (HTTP {resp.status_code}): {resp.text}")
        return None
    data = resp.json()
    file_id = data.get("data", {}).get("file_id")
    if not file_id:
        logger.error(f"Upload succeeded but no file_id in response: {data}")
    return file_id


async def upload_file_bytes(token: str, file_bytes: bytes, filename: str, file_type: str = "image") -> Optional[str]:
    url = f"{QWEN_BASE}/api/v2/files/upload"
    headers = {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {token}",
    }
    client = _get_upload_client()
    files = {"file": (filename, file_bytes)}
    resp = await client.post(url, headers=headers, files=files)
    if resp.status_code != 200:
        logger.error(f"Upload failed (HTTP {resp.status_code}): {resp.text}")
        return None
    data = resp.json()
    file_id = data.get("data", {}).get("file_id")
    if not file_id:
        logger.error(f"Upload succeeded but no file_id in response: {data}")
    return file_id


DATA_URI_RE = re.compile(r"^data:(image/\w+);base64,(.+)$")
_download_client: Optional[httpx.AsyncClient] = None


def _get_download_client() -> httpx.AsyncClient:
    global _download_client
    if _download_client is None:
        _download_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    return _download_client


async def upload_image_url(token: str, image_url: str) -> Optional[str]:
    match = DATA_URI_RE.match(image_url)
    if match:
        mime = match.group(1)
        b64_data = match.group(2)
        ext = mime.split("/")[-1].replace("jpeg", "jpg")
        try:
            file_bytes = base64.b64decode(b64_data)
        except Exception as e:
            logger.error(f"Failed to decode base64 image: {e}")
            return None
        return await upload_file_bytes(token, file_bytes, f"image.{ext}", file_type="image")
    else:
        try:
            client = _get_download_client()
            resp = await client.get(image_url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/png")
            ext = content_type.split("/")[-1].split(";")[0].replace("jpeg", "jpg")
            return await upload_file_bytes(token, resp.content, f"image.{ext}", file_type="image")
        except Exception as e:
            logger.error(f"Failed to download image from {image_url[:60]}: {e}")
            return None
