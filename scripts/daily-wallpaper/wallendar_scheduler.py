# pip install requests Pillow

"""
wallendar_scheduler.py
----------------------
Daily wallpaper auto-updater for Wallendar.
Calls the /api/create endpoint, saves the PNG, and sets it as the Windows wallpaper.
Rotates through all available sample backgrounds on each run.

Usage:
    python wallendar_scheduler.py                        # interactive resolution prompt
    python wallendar_scheduler.py --resolution desktop-fhd  # non-interactive

Resolution keys:
    desktop-hd   1280x720     desktop-fhd  1920x1080    desktop-4k   3840x2160
    mobile-hd    720x1280     mobile-fhd   1080x1920    mobile-4k    1440x2560

Intended to be run by Windows Task Scheduler once per day at 12:00 AM.
"""

import argparse
import ctypes
import io
import json
import os
import sys
from datetime import datetime

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

# Resolution presets: key → (width, height, viewMode)
# viewMode controls calendar layout proportions sent to the API.
RESOLUTIONS = {
    "desktop-hd":  (1280,  720,  "desktop"),
    "desktop-fhd": (1920,  1080, "desktop"),
    "desktop-4k":  (3840,  2160, "desktop"),
    "mobile-hd":   (720,   1280, "mobile"),
    "mobile-fhd":  (1080,  1920, "mobile"),
    "mobile-4k":   (1440,  2560, "mobile"),
}

DEFAULT_RESOLUTION = "desktop-fhd"

# State file: persists background rotation index + last chosen resolution.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(_SCRIPT_DIR, "wallendar_state.json")

# Server-side hard limit — safety net in case a custom URL is added above.
MAX_IMAGE_DIMENSION = 4096

# Output path — resolved dynamically so it works for any Windows user account.
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
# State — background rotation + resolution preference
# ---------------------------------------------------------------------------

def _read_state() -> dict:
    """Load persisted state from STATE_FILE, or return defaults."""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_index": -1, "resolution": None}


def _write_state(state: dict) -> None:
    """Persist state dict to STATE_FILE, silently ignoring write errors."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
    except OSError:
        pass  # Non-fatal — state just resets on next run


def pick_next_background() -> tuple:
    """Return (url, human_label) for the next background in round-robin order."""
    state = _read_state()
    last = state.get("last_index", -1)
    next_index = (last + 1) % len(BACKGROUND_IMAGES)
    state["last_index"] = next_index
    _write_state(state)
    url = BACKGROUND_IMAGES[next_index]
    label = f"{next_index + 1}/{len(BACKGROUND_IMAGES)}"
    return url, label


# ---------------------------------------------------------------------------
# Resolution selection
# ---------------------------------------------------------------------------

# Ordered list used to build the interactive menu (stable display order).
_RESOLUTION_MENU = [
    ("desktop-hd",  "Desktop HD   — 1280 × 720"),
    ("desktop-fhd", "Desktop FHD  — 1920 × 1080  [default]"),
    ("desktop-4k",  "Desktop 4K   — 3840 × 2160"),
    ("mobile-hd",   "Mobile HD    — 720  × 1280"),
    ("mobile-fhd",  "Mobile FHD   — 1080 × 1920"),
    ("mobile-4k",   "Mobile 4K    — 1440 × 2560"),
]


def _prompt_resolution() -> str:
    """Show an interactive numbered menu and return the chosen resolution key."""
    print("\nSelect wallpaper resolution:")
    for i, (key, label) in enumerate(_RESOLUTION_MENU, start=1):
        print(f"  {i}) {label}")
    print()

    while True:
        raw = input(f"Enter choice [1-{len(_RESOLUTION_MENU)}] (default=2): ").strip()
        if raw == "":
            return DEFAULT_RESOLUTION
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(_RESOLUTION_MENU):
                return _RESOLUTION_MENU[idx][0]
        print(f"  Invalid input — enter a number between 1 and {len(_RESOLUTION_MENU)}.")


def resolve_resolution(arg_value: str | None) -> str:
    """Determine the resolution to use, in priority order:

    1. --resolution CLI argument (set by Task Scheduler or direct call)
    2. Last saved preference in wallendar_state.json
    3. Interactive prompt (only reached on a direct run with no saved state)
    """
    # Priority 1: explicit CLI argument
    if arg_value is not None:
        if arg_value not in RESOLUTIONS:
            _fail(
                f"Unknown resolution {arg_value!r}. "
                f"Valid options: {', '.join(RESOLUTIONS)}"
            )
        return arg_value

    # Priority 2: saved preference from a previous interactive run
    state = _read_state()
    saved = state.get("resolution")
    if saved and saved in RESOLUTIONS:
        return saved

    # Priority 3: interactive prompt (direct manual run, first time)
    chosen = _prompt_resolution()

    # Persist the choice so future automated runs use it without prompting
    state["resolution"] = chosen
    _write_state(state)
    return chosen


# ---------------------------------------------------------------------------
# Config builder
# ---------------------------------------------------------------------------

def _build_config(view_mode: str) -> str:
    """Return the calendar config JSON string for the given viewMode."""
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
        "viewMode": view_mode,   # Derived from chosen resolution
        "calendarScale": 1,
        "showHighlight": True,
        "showStrikethrough": True,
        # date intentionally omitted — server auto-detects today
    }
    return json.dumps(config)


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------

def download_background_image(url: str) -> bytes:
    """Download background image locally and return raw bytes.

    Uploading raw bytes avoids the server-side URL fetch path which goes
    through SSRF protection and can fail depending on hosting environment.
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


def resize_to_resolution(image_bytes: bytes, target_w: int, target_h: int) -> bytes:
    """Resize and center-crop the image to exactly (target_w x target_h).

    Uses a cover strategy — scales the image so both dimensions are >= target,
    then crops the excess from the centre. This fills the canvas completely
    without letterboxing or distortion, identical to CSS background-size: cover.

    Resampling: LANCZOS (highest quality, sinc-based downscale filter).
    Output:     JPEG at quality 92 (high quality, well within human perception).
    """
    img = Image.open(io.BytesIO(image_bytes))
    src_w, src_h = img.size

    # Scale so the shorter side (relative to target) hits the target exactly
    scale = max(target_w / src_w, target_h / src_h)
    scaled_w = int(src_w * scale)
    scaled_h = int(src_h * scale)

    if (scaled_w, scaled_h) != (src_w, src_h):
        _log(
            f"Resizing background: {src_w}×{src_h} → {scaled_w}×{scaled_h} "
            f"(target: {target_w}×{target_h})"
        )
        img = img.resize((scaled_w, scaled_h), Image.LANCZOS)

    # Center crop to exact target dimensions
    left = (scaled_w - target_w) // 2
    top  = (scaled_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def safety_clamp(image_bytes: bytes) -> bytes:
    """Safety net: reject images still over the server hard limit after resize.

    Under normal operation this should never trigger because all RESOLUTIONS
    presets are within 4096×4096. Guards against custom URLs added to
    BACKGROUND_IMAGES that could be unusually large.
    """
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
        _fail(
            f"Image dimensions {w}×{h} still exceed server limit "
            f"({MAX_IMAGE_DIMENSION}px) after resize — aborting."
        )
    return image_bytes


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def fetch_wallpaper(image_bytes: bytes, view_mode: str) -> bytes:
    """POST image bytes + config to the Wallendar API; return raw PNG bytes."""
    config_json = _build_config(view_mode)

    try:
        response = requests.post(
            API_URL,
            files={
                "image":  ("background.jpg", image_bytes, "image/jpeg"),
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


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_wallpaper(png_bytes: bytes) -> None:
    """Write PNG bytes to WALLPAPER_PATH, overwriting any existing file."""
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

    SystemParametersInfoW action codes:
        20 = SPI_SETDESKWALLPAPER
         3 = SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
    """
    abs_path = os.path.abspath(path)
    result = ctypes.windll.user32.SystemParametersInfoW(20, 0, abs_path, 3)
    if result == 0:
        error_code = ctypes.get_last_error()
        _fail(
            f"SystemParametersInfoW failed (return=0, last_error={error_code}). "
            f"Wallpaper PNG was saved but could not be applied."
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and set a Wallendar calendar wallpaper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Resolution options:\n"
            "  desktop-hd   1280×720      desktop-fhd  1920×1080   desktop-4k  3840×2160\n"
            "  mobile-hd    720×1280      mobile-fhd   1080×1920   mobile-4k   1440×2560\n"
        ),
    )
    parser.add_argument(
        "--resolution", "-r",
        metavar="KEY",
        default=None,
        help=(
            "Wallpaper resolution key (e.g. desktop-fhd). "
            "If omitted, uses the last saved preference or prompts interactively."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # 1. Determine resolution
    res_key = resolve_resolution(args.resolution)
    target_w, target_h, view_mode = RESOLUTIONS[res_key]
    _log(f"Resolution: {res_key} ({target_w}×{target_h}, viewMode={view_mode})")

    # 2. Pick next background in rotation
    bg_url, bg_label = pick_next_background()
    _log(f"Background {bg_label}: {bg_url}")

    # 3. Download → resize to exact target resolution → safety check
    image_bytes = download_background_image(bg_url)
    image_bytes = resize_to_resolution(image_bytes, target_w, target_h)
    image_bytes = safety_clamp(image_bytes)

    # 4. Generate wallpaper via API
    png_bytes = fetch_wallpaper(image_bytes, view_mode)

    # 5. Save and apply
    save_wallpaper(png_bytes)
    set_windows_wallpaper(WALLPAPER_PATH)
    _log(f"Wallpaper updated successfully → {WALLPAPER_PATH}")


if __name__ == "__main__":
    main()
