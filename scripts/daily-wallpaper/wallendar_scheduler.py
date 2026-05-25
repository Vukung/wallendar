# pip install requests Pillow

"""
wallendar_scheduler.py
----------------------
Daily wallpaper auto-updater for Wallendar.
Calls the /api/create endpoint, saves the PNG, and sets it as the Windows wallpaper.
Rotates through all available sample backgrounds on each run.

Usage:
    python wallendar_scheduler.py

Intended to be run by Windows Task Scheduler once per day at 12:00 PM.
"""

import ctypes
import json
import os
import sys
from datetime import datetime

import io

import requests
from PIL import Image

# ---------------------------------------------------------------------------
# Configuration — edit these to customise behaviour
# ---------------------------------------------------------------------------

API_URL = "https://www.wallendar.shop/api/create"

# All available Wallendar sample backgrounds — rotated in order on each run.
# Add or remove URLs here to change the rotation pool.
BACKGROUND_IMAGES = [
    "https://www.wallendar.shop/samples/sample-bg1.jpg",
    "https://www.wallendar.shop/samples/sample-bg2.jpg",
    "https://www.wallendar.shop/samples/sample-bg3.jpg",
    "https://www.wallendar.shop/samples/sample-bg4.jpg",
    "https://www.wallendar.shop/samples/sample-bg5.jpg",
    "https://www.wallendar.shop/samples/sample-bg6.jpg",
    "https://www.wallendar.shop/samples/sample-bg7.jpg",
]

# State file stores the index of the last-used background so rotation persists
# across separate script invocations.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(_SCRIPT_DIR, "wallendar_state.json")

# Server-side hard limit — images exceeding either dimension are rejected.
# We resize locally before uploading to stay safely within bounds.
MAX_IMAGE_DIMENSION = 4096

# Resolved once at startup so every log line uses the same path.
WALLPAPER_PATH = os.path.join(
    os.path.expanduser("~"), "Pictures", "wallendar_today.png"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(message: str) -> None:
    """Print a timestamped status line to stdout."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}")


def _fail(reason: str) -> None:
    """Print a timestamped error line to stderr and exit with code 1."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] ERROR: {reason}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Background rotation state
# ---------------------------------------------------------------------------

def _read_state() -> dict:
    """Load persisted state from STATE_FILE, or return defaults."""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_index": -1}


def _write_state(state: dict) -> None:
    """Persist state dict to STATE_FILE, silently ignoring write errors."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
    except OSError:
        pass  # Non-fatal — rotation just resets next run


def pick_next_background() -> tuple:
    """Return (url, human_label) for the next background in rotation.

    Reads the last-used index from STATE_FILE, advances it by one
    (wrapping around), saves the new index, and returns the chosen URL.
    """
    state = _read_state()
    last = state.get("last_index", -1)
    next_index = (last + 1) % len(BACKGROUND_IMAGES)
    _write_state({"last_index": next_index})
    url = BACKGROUND_IMAGES[next_index]
    label = f"{next_index + 1}/{len(BACKGROUND_IMAGES)}"
    return url, label


def _build_config() -> str:
    """Return the calendar config JSON string with the current month/year."""
    now = datetime.now()
    config = {
        "month": now.month - 1,  # API expects 0-indexed month (0 = January)
        "year": now.year,
        "weekStart": "sunday",
        "headerFormat": "full",
        "textColor": "#ffffff",
        "fontFamily": "Product Sans",
        "offsetX": 0,
        "offsetY": 0,
        "viewMode": "desktop",
        "calendarScale": 1,
        "showHighlight": True,
        "showStrikethrough": True,
        # date is intentionally omitted — server auto-detects today
    }
    return json.dumps(config)


# ---------------------------------------------------------------------------
# Core steps
# ---------------------------------------------------------------------------

def download_background_image(url: str) -> bytes:
    """Download the background image locally so we can upload it as binary.

    Accepts an explicit URL so the caller controls which background to use.
    Uploading raw bytes avoids the server-side URL fetch path (which goes
    through SSRF protection and can fail on certain hosts/networks).
    """
    try:
        response = requests.get(url, timeout=30)
    except requests.exceptions.ConnectionError as exc:
        _fail(f"Network error while downloading background image — {exc}")
    except requests.exceptions.Timeout:
        _fail("Timed out downloading background image (30s limit)")
    except requests.exceptions.RequestException as exc:
        _fail(f"Unexpected error downloading background image — {exc}")

    if response.status_code != 200:
        _fail(
            f"Failed to download background image: "
            f"HTTP {response.status_code} from {url}"
        )

    return response.content


def resize_if_needed(image_bytes: bytes) -> bytes:
    """Resize image so neither dimension exceeds MAX_IMAGE_DIMENSION.

    Preserves aspect ratio using LANCZOS resampling. Returns the original
    bytes unchanged if no resize is needed, avoiding a lossy re-encode.
    """
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size

    if w <= MAX_IMAGE_DIMENSION and h <= MAX_IMAGE_DIMENSION:
        return image_bytes  # Already within limits — skip re-encode

    # Scale down proportionally so the longer side hits the limit exactly
    scale = MAX_IMAGE_DIMENSION / max(w, h)
    new_size = (int(w * scale), int(h * scale))
    _log(f"Resizing image from {w}x{h} to {new_size[0]}x{new_size[1]} (server limit: {MAX_IMAGE_DIMENSION}px)")

    img = img.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    # Preserve format where possible; fall back to JPEG for unknown types
    fmt = img.format or "JPEG"
    if fmt.upper() == "JPEG":
        img.save(buf, format="JPEG", quality=92)
    else:
        img.save(buf, format=fmt)
    return buf.getvalue()


def fetch_wallpaper(image_bytes: bytes) -> bytes:
    """POST image bytes + config to the Wallendar API; return raw PNG bytes."""
    config_json = _build_config()

    try:
        response = requests.post(
            API_URL,
            files={
                # Upload the image as binary data — server receives it as a File
                "image": ("background.jpg", image_bytes, "image/jpeg"),
                # config must be a plain form field, not a file attachment
                "config": (None, config_json),
            },
            timeout=60,
        )
    except requests.exceptions.ConnectionError as exc:
        _fail(f"Network error while calling API — {exc}")
    except requests.exceptions.Timeout:
        _fail("Request to Wallendar API timed out after 60 seconds")
    except requests.exceptions.RequestException as exc:
        _fail(f"Unexpected request error — {exc}")

    if response.status_code != 200:
        # Try to surface the API's error message if it returned JSON
        try:
            detail = response.json().get("error", response.text)
        except Exception:
            detail = response.text or f"HTTP {response.status_code}"
        _fail(f"API returned {response.status_code}: {detail}")

    content_type = response.headers.get("Content-Type", "")
    if "image" not in content_type.lower():
        _fail(
            f"API response does not look like an image "
            f"(Content-Type: {content_type!r})"
        )

    return response.content


def save_wallpaper(png_bytes: bytes) -> None:
    """Write the PNG bytes to WALLPAPER_PATH, overwriting any existing file."""
    # Ensure the Pictures directory exists (it almost always does, but be safe)
    pictures_dir = os.path.dirname(WALLPAPER_PATH)
    try:
        os.makedirs(pictures_dir, exist_ok=True)
    except OSError as exc:
        _fail(f"Could not create directory {pictures_dir!r} — {exc}")

    try:
        with open(WALLPAPER_PATH, "wb") as fh:
            fh.write(png_bytes)
    except OSError as exc:
        _fail(f"Could not write wallpaper to {WALLPAPER_PATH!r} — {exc}")


def set_windows_wallpaper(path: str) -> None:
    """Apply the PNG at *path* as the Windows desktop wallpaper.

    SystemParametersInfoW action code 20 = SPI_SETDESKWALLPAPER
    fWinIni flag  3  = SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
    """
    abs_path = os.path.abspath(path)
    result = ctypes.windll.user32.SystemParametersInfoW(20, 0, abs_path, 3)
    if result == 0:
        # Non-zero means success; 0 means the call failed.
        error_code = ctypes.get_last_error()
        _fail(
            f"SystemParametersInfoW failed (return=0, last_error={error_code}). "
            f"Wallpaper file was saved but could not be applied."
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    bg_url, bg_label = pick_next_background()
    _log(f"Background {bg_label}: {bg_url}")

    image_bytes = download_background_image(bg_url)
    image_bytes = resize_if_needed(image_bytes)
    png_bytes = fetch_wallpaper(image_bytes)
    save_wallpaper(png_bytes)
    set_windows_wallpaper(WALLPAPER_PATH)
    _log(f"Wallpaper updated successfully \u2192 {WALLPAPER_PATH}")


if __name__ == "__main__":
    main()
