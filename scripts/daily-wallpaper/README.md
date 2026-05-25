# Wallendar Daily Wallpaper Scheduler

Automatically generates a calendar wallpaper every day using the [Wallendar](https://www.wallendar.shop) API and sets it as your Windows desktop background. Backgrounds rotate through all available Wallendar sample images on each run.

---

## Files in This Folder

```
scripts/daily-wallpaper/
├── wallendar_scheduler.py   # Main Python script — does all the work
├── setup_task_scheduler.bat # One-time installer — registers Windows tasks
├── wallendar_state.json     # Auto-created — tracks background rotation index
└── README.md                # This file
```

---

## Quick Start

### 1. Install dependencies (one-time)

```bash
pip install requests Pillow
```

### 2. Test the script manually

```bash
python scripts\daily-wallpaper\wallendar_scheduler.py
```

### 3. Install the scheduled tasks (one-time, run as Administrator)

Right-click `setup_task_scheduler.bat` → **Run as administrator**

That's it. The wallpaper will now update automatically every day at midnight and on every logon.

---

## How the Script Works — Step by Step

### Step 1 — Pick the next background (`pick_next_background`)

The script maintains a rotation through 7 sample backgrounds. On every run it:

1. Reads `wallendar_state.json` from the same folder as the script.
2. Retrieves `last_index` (defaults to `-1` if the file doesn't exist yet).
3. Computes `next_index = (last_index + 1) % 7` — wraps back to 0 after the 7th image.
4. Writes the new index back to the state file immediately (before the API call), so a failed run still advances the rotation.
5. Returns the URL of the chosen background and a human label like `"3/7"`.

**Rotation pool (in order):**

| # | URL |
|---|-----|
| 1 | `https://www.wallendar.shop/samples/sample-bg1.jpg` |
| 2 | `https://www.wallendar.shop/samples/sample-bg2.jpg` |
| 3 | `https://www.wallendar.shop/samples/sample-bg3.jpg` |
| 4 | `https://www.wallendar.shop/samples/sample-bg4.jpg` |
| 5 | `https://www.wallendar.shop/samples/sample-bg5.jpg` |
| 6 | `https://www.wallendar.shop/samples/sample-bg6.jpg` |
| 7 | `https://www.wallendar.shop/samples/sample-bg7.jpg` |

To add your own images, append any publicly accessible JPEG/PNG URL to the `BACKGROUND_IMAGES` list in `wallendar_scheduler.py`.

---

### Step 2 — Download the background image (`download_background_image`)

The chosen background URL is downloaded **locally** by the script (a simple `GET` request with a 30-second timeout) and stored as raw bytes in memory.

> **Why not just pass the URL directly to the API?**
>
> The Wallendar API supports a URL-mode where you pass the image as a string field. However, the server fetches that URL server-side through an SSRF protection layer (`fetchSafeImage` in `lib/fetch-safe.ts`). This layer pins DNS resolution and enforces strict IP filtering, which can fail depending on the hosting environment's network topology. Downloading the image locally and uploading the bytes directly is more reliable and completely sidesteps that code path.

---

### Step 3 — Resize if needed (`resize_if_needed`)

The Wallendar API enforces these hard limits on uploaded images (defined in `lib/server-canvas.ts`):

| Limit | Value |
|---|---|
| Maximum width | **4096 px** |
| Maximum height | **4096 px** |
| Maximum total pixels | **16,000,000 px** (≈ 4000×4000) |

Images that exceed either dimension are rejected with HTTP 400 (`Image dimensions exceed maximum limits`).

The script handles this automatically before uploading:

1. Opens the downloaded bytes with **Pillow** (`PIL.Image`).
2. Reads the actual pixel dimensions (`w`, `h`).
3. If **both** dimensions are within 4096 px, the original bytes are returned unchanged (no re-encode, no quality loss).
4. If **either** dimension exceeds 4096 px, a scale factor is computed:
   ```
   scale = 4096 / max(w, h)
   ```
   This ensures the **longer side** is clamped to exactly 4096 px while the shorter side shrinks proportionally, preserving the original aspect ratio.
5. The image is resampled using **LANCZOS** (the highest quality downscaling algorithm available in Pillow — equivalent to a sinc filter).
6. The result is re-encoded as **JPEG at quality 92** (high quality, significantly smaller than lossless) and returned as bytes.

**Example:** A `6000×4000` image becomes `4096×2731`. A `3840×2160` image passes through unchanged.

---

### Step 4 — Call the API (`fetch_wallpaper`)

A `POST` request is made to:

```
https://www.wallendar.shop/api/create
```

**Request format:** `multipart/form-data` with two fields:

| Field | Type | Value |
|---|---|---|
| `image` | File (binary) | The JPEG bytes with filename `background.jpg` and MIME type `image/jpeg` |
| `config` | String (JSON) | The calendar configuration object (see below) |

**Calendar configuration sent on every run:**

```json
{
  "month":            <0-indexed current month>,
  "year":             <current year as integer>,
  "weekStart":        "sunday",
  "headerFormat":     "full",
  "textColor":        "#ffffff",
  "fontFamily":       "Product Sans",
  "offsetX":          0,
  "offsetY":          0,
  "viewMode":         "desktop",
  "calendarScale":    1,
  "showHighlight":    true,
  "showStrikethrough": true
}
```

**Parameter reference:**

| Parameter | Type | Range / Options | Description |
|---|---|---|---|
| `month` | `number` | `0–11` | **0-indexed** month. January = `0`, December = `11`. Computed from `datetime.now().month - 1` at runtime. |
| `year` | `number` | `1000–9999` | Full 4-digit year. Computed from `datetime.now().year` at runtime. |
| `weekStart` | `string` | `"sunday"` \| `"monday"` | Which day the calendar week starts on. |
| `headerFormat` | `string` | See table below | Controls how the month/year header is formatted. |
| `textColor` | `string` | Any `#RRGGBB` hex | Color of all calendar text (month name, day labels, date numbers). |
| `fontFamily` | `string` | See font list below | Typeface used for all calendar text. |
| `offsetX` | `number` | `-1.0` to `1.0` | Horizontal position of the calendar on the wallpaper. `0` = centred, `-1` = far left, `1` = far right. |
| `offsetY` | `number` | `-1.0` to `1.0` | Vertical position of the calendar. `0` = centred, `-1` = top, `1` = bottom. |
| `viewMode` | `string` | `"desktop"` \| `"mobile"` | Controls layout proportions. `"desktop"` is wider; `"mobile"` is taller. |
| `calendarScale` | `number` | `0.5` to `1.5` | Uniform scale multiplier for the entire calendar overlay. `1.0` = default size. |
| `showHighlight` | `boolean` | `true` \| `false` | When `true`, draws a filled circle behind today's date number using the `textColor` at 100% opacity. The date number itself is rendered in a contrasting colour (black or white) for legibility. |
| `showStrikethrough` | `boolean` | `true` \| `false` | When `true`, renders all past dates (days before today) at 40% opacity with a horizontal strikethrough line at 40% opacity drawn over them. |
| `date` | `number` | `1–31` (optional) | **Not sent by this script.** When omitted, the server auto-detects today's date by comparing `month`/`year` against the server's current date. If the month/year don't match the current month, no date effects are applied. |

**`headerFormat` options:**

| Value | Example output |
|---|---|
| `"full"` | `MAY 2026` |
| `"short"` | `MAY 26` |
| `"numeric"` | `5 / 26` |
| `"numeric-full-year"` | `5 / 2026` |
| `"numeric-short-year"` | `5 / 26` |
| `"short-short-year"` | `MAY 26` |
| `"short-full-year"` | `MAY 2026` |

**Available `fontFamily` values:**

- `Product Sans` *(default)*
- `Montserrat`
- `Doto`
- `Crafty Girls`
- `Freckle Face`
- `Playwrite CA`
- `Segoe Script`
- `Instrument Serif`
- `Ultra`

**API response:**

On success, the server returns `HTTP 200` with `Content-Type: image/png` and a `Content-Disposition: attachment` header. The body is the raw PNG file of the rendered wallpaper at the same resolution as the uploaded background image (after server-side resizing if applicable).

On failure, the server returns a JSON body `{ "error": "..." }` with an appropriate HTTP status code (`400` for bad input, `429` for rate limiting, `500` for server errors).

---

### Step 5 — Save the PNG (`save_wallpaper`)

The PNG bytes returned by the API are written to:

```
C:\Users\<USERNAME>\Pictures\wallendar_today.png
```

`<USERNAME>` is resolved dynamically using `os.path.expanduser("~")`, so the script works for any Windows user account without hardcoding a path. The `Pictures` directory is created if it doesn't already exist. The file is overwritten silently on every run.

---

### Step 6 — Set as Windows wallpaper (`set_windows_wallpaper`)

The script calls the Windows User32 API directly via Python's `ctypes` module:

```python
ctypes.windll.user32.SystemParametersInfoW(20, 0, abs_path, 3)
```

| Argument | Value | Meaning |
|---|---|---|
| `uiAction` | `20` (`SPI_SETDESKWALLPAPER`) | Tells Windows to change the desktop wallpaper |
| `uiParam` | `0` | Unused for this action |
| `pvParam` | Absolute path to the PNG | Full path string of the wallpaper file |
| `fWinIni` | `3` | `SPIF_UPDATEINIFILE (1) \| SPIF_SENDCHANGE (2)` — saves the change to the registry and broadcasts the change to all open windows immediately |

The absolute path is always used (via `os.path.abspath`) to avoid ambiguity regardless of the working directory at call time. A return value of `0` from this call indicates failure; the script reads the Windows last-error code and exits with a clear message.

---

### Logging

Every log line is prefixed with a timestamp in `[YYYY-MM-DD HH:MM:SS]` format.

**Successful run output:**
```
[2026-05-24 00:00:01] Background 3/7: https://www.wallendar.shop/samples/sample-bg3.jpg
[2026-05-24 00:00:06] Resizing image from 6000x4000 to 4096x2731 (server limit: 4096px)
[2026-05-24 00:00:21] Wallpaper updated successfully → C:\Users\Utkarsh\Pictures\wallendar_today.png
```

**Failed run output (stderr, exits with code 1):**
```
[2026-05-24 00:00:05] ERROR: API returned 400: Invalid configuration parameters
```

---

## How the Scheduler Works

`setup_task_scheduler.bat` registers **two** Windows Task Scheduler tasks when run once as Administrator:

### Task 1 — `WallendarDailyUpdate`

| Property | Value |
|---|---|
| Trigger | Every day at **12:00 AM** (midnight) |
| Action | `python "...\wallendar_scheduler.py"` |
| Run as | `SYSTEM` account |
| Works without login | ✅ Yes |
| Priority | Highest |

Fires at midnight so your wallpaper is fresh when you start your day.

### Task 2 — `WallendarOnLogon`

| Property | Value |
|---|---|
| Trigger | **Every user logon** + 1-minute delay |
| Action | `python "...\wallendar_scheduler.py"` |
| Run as | Currently logged-in user |
| Works without login | ❌ No (by design — needs a user session) |
| Priority | Highest |

The 1-minute delay gives Windows time to fully load the desktop, network connectivity, and the user shell before the script runs. Without this delay, the wallpaper API call can fail on slower machines because the network isn't ready yet.

This task covers the case where you boot your PC after midnight but before the next midnight trigger — for example, if you shut down at 10 PM and boot at 8 AM the following day, the midnight task won't have run, but the logon task will fire 1 minute after you log in and update the wallpaper.

### How the bat finds Python

The script uses `where python` to locate the Python executable dynamically:

```bat
for /f "tokens=*" %%P in ('where python 2^>nul') do (
    set "PYTHON_EXE=%%P"
    goto :found_python
)
```

This means the registered task always uses the full absolute path to your Python installation (e.g. `C:\Users\Utkarsh\AppData\Local\Programs\Python\Python313\python.exe`), not just `python`. This avoids PATH-related failures when Task Scheduler runs tasks in a minimal environment.

### The bat self-locates

```bat
set "SCRIPT_DIR=%~dp0"
```

`%~dp0` expands to the full path of the directory containing the bat file itself, regardless of where you double-click it from. This means the registered task always has the correct absolute path to `wallendar_scheduler.py` — you can place the folder anywhere and it will work.

---

## Customising the Script

All user-editable settings are at the top of `wallendar_scheduler.py`:

```python
# Change the API endpoint (e.g. for local development)
API_URL = "https://www.wallendar.shop/api/create"

# Add/remove/reorder backgrounds in the rotation pool
BACKGROUND_IMAGES = [
    "https://www.wallendar.shop/samples/sample-bg1.jpg",
    ...
]

# Where the wallpaper PNG is saved
WALLPAPER_PATH = os.path.join(os.path.expanduser("~"), "Pictures", "wallendar_today.png")

# Server-side image size limit (don't raise this without changing the server too)
MAX_IMAGE_DIMENSION = 4096
```

To change calendar appearance, edit the dict inside `_build_config()`. Refer to the parameter table above for all valid values.

---

## State File

`wallendar_state.json` is created automatically next to the script on the first run. It contains a single key:

```json
{
  "last_index": 2
}
```

This is the 0-based index of the **last used** background. On the next run, index `3` (i.e. `sample-bg4.jpg`) will be used.

- **To reset the rotation** back to `sample-bg1.jpg`: delete this file or set `"last_index": -1`.
- **If the file is missing or corrupted**: the script silently resets to index `0` (the first background) and continues normally.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `requests` | Any modern | HTTP client — downloads background images, POSTs to the API |
| `Pillow` | Any modern | Image processing — reads dimensions, resizes oversized images |
| Standard library | Python 3.8+ | `ctypes`, `json`, `os`, `sys`, `datetime`, `io` |

Install with:
```bash
pip install requests Pillow
```

---

## Troubleshooting

| Error | Likely cause | Fix |
|---|---|---|
| `API returned 400: Image dimensions exceed maximum limits` | Background image is larger than 4096×4096 px | Should be auto-fixed by `resize_if_needed`. Check Pillow is installed. |
| `API returned 400: Invalid configuration parameters` | A config value is out of range or uses an invalid font/format | Check the parameter table above for valid values. |
| `API returned 429` | Rate limit hit (too many requests in a short window) | Wait a few minutes and try again. |
| `Network error while downloading background image` | No internet connection, or the background URL is unreachable | Check connectivity. Verify the URL returns 200 in a browser. |
| `SystemParametersInfoW failed` | Windows rejected the wallpaper call | Ensure the PNG path exists and is a valid image. Try running the script as Administrator. |
| Task doesn't fire at midnight | Task Scheduler service is stopped, or PC is off at midnight | The logon task will pick it up the next time you log in. |
| `Python was not found on PATH` | Python not installed or not on PATH when bat was run | Install Python and tick "Add to PATH" during installation, then re-run the bat. |
