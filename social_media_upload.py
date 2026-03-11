#!/usr/bin/env python3
"""
Social Media Auto-Upload Tool
Uploads images to TikTok and Instagram via the Upload-Post API.
Supports folder selection, scheduling, and platform-specific captions.
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

import requests

# Load .env if available (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
BASE_DIRECTORY = os.environ.get(
    "UPLOAD_BASE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiktok_output"),
)
API_KEY = os.environ.get("UPLOAD_POST_API_KEY")
# Sandbox: set UPLOAD_POST_USE_SANDBOX=1 and optionally SANDBOX_API_BASE_URL (default below)
USE_SANDBOX = os.environ.get("UPLOAD_POST_USE_SANDBOX", "").strip().lower() in ("1", "true", "yes")
SANDBOX_API_BASE_URL = os.environ.get(
    "SANDBOX_API_BASE_URL",
    "https://api-sandbox.upload-post.com/api",  # override if Upload-Post gives a different URL
)
API_BASE_URL = SANDBOX_API_BASE_URL if USE_SANDBOX else "https://api.upload-post.com/api"
API_UPLOAD_URL = f"{API_BASE_URL}/upload_photos"
API_ME_URL = f"{API_BASE_URL}/uploadposts/me"
UPLOAD_POST_USER = os.environ.get("UPLOAD_POST_USER", "mybrand")
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upload_history.json")

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
INSTAGRAM_CAROUSEL_MAX = 10


# -----------------------------------------------------------------------------
# Core functions
# -----------------------------------------------------------------------------
def validate_api_key() -> bool:
    """Check API key validity by calling the Current User endpoint."""
    if not API_KEY or not API_KEY.strip():
        print("Error: UPLOAD_POST_API_KEY environment variable is not set.")
        print("Set it with: set UPLOAD_POST_API_KEY=your-key (Windows) or export UPLOAD_POST_API_KEY=your-key (Unix)")
        return False
    if USE_SANDBOX:
        print(f"Sandbox mode: using base URL {API_BASE_URL}")
    try:
        resp = requests.get(
            API_ME_URL,
            headers={"Authorization": f"Apikey {API_KEY}"},
            timeout=10,
        )
        if resp.status_code == 401:
            print("Error: Invalid or expired API key.")
            return False
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Error validating API key: {e}")
        return False


def get_folder_path() -> Optional[Path]:
    """Interactive folder selection from the base directory. Returns Path or None."""
    base = Path(BASE_DIRECTORY)
    if not base.is_dir():
        print(f"Error: Base directory does not exist: {base}")
        return None

    print(f"\nBase directory: {base.resolve()}")
    name = input("Enter folder name (relative to base, or full path): ").strip()
    if not name:
        print("No folder name entered.")
        return None

    path = base / name
    if not path.is_dir():
        # Allow absolute path
        path = Path(name)
    if not path.is_dir():
        print(f"Error: Folder not found: {path}")
        return None
    return path


def get_image_files(folder_path: Path) -> list[Path]:
    """Retrieve image paths from folder, sorted by filename. Supports .jpg, .jpeg, .png, .webp."""
    files = []
    for p in folder_path.iterdir():
        if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            files.append(p)
    return sorted(files, key=lambda x: x.name)


def display_folder_contents(image_paths: list[Path]) -> None:
    """Display list of images that will be uploaded."""
    if not image_paths:
        return
    print(f"\nFound {len(image_paths)} image(s) in folder:")
    for i, p in enumerate(image_paths, 1):
        print(f"  {i}. {p.name}")


def get_upload_config(image_count: int) -> dict:
    """Interactive prompts for title, description, platforms, optional titles, TikTok song, etc."""
    config = {}

    config["title"] = input("\nEnter title (main caption): ").strip() or "My Post"
    config["description"] = input("Enter description (with hashtags): ").strip()

    print("\nSelect platforms:")
    print("  [1] TikTok only")
    print("  [2] Instagram only")
    print("  [3] Both")
    choice = input("Choice (1/2/3): ").strip() or "3"
    if choice == "1":
        config["platforms"] = ["tiktok"]
    elif choice == "2":
        config["platforms"] = ["instagram"]
    else:
        config["platforms"] = ["tiktok", "instagram"]

    tiktok_title = input("TikTok-specific title (press Enter to use default): ").strip()
    if tiktok_title:
        config["tiktok_title"] = tiktok_title

    instagram_title = input("Instagram-specific title (press Enter to use default): ").strip()
    if instagram_title:
        config["instagram_title"] = instagram_title

    config["tiktok_song"] = input("TikTok song (optional, name or ID; press Enter to skip): ").strip()

    return config


def schedule_or_now() -> tuple[bool, Optional[str], Optional[str]]:
    """
    Prompt for upload now or schedule. Returns (upload_now, scheduled_date_iso, timezone).
    scheduled_date_iso is only set when scheduling.
    """
    print("\nUpload timing:")
    print("  [1] Upload now")
    print("  [2] Schedule for later")
    choice = input("Choice (1/2): ").strip() or "1"

    if choice != "2":
        return True, None, None

    date_str = input("Enter date (YYYY-MM-DD): ").strip()
    time_str = input("Enter time (HH:MM): ").strip()
    timezone_str = input("Enter timezone (e.g. America/New_York): ").strip() or "UTC"

    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        # Build ISO string; API will interpret with timezone
        scheduled_iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
        return False, scheduled_iso, timezone_str
    except ValueError:
        print("Invalid date/time. Use YYYY-MM-DD and HH:MM.")
        return True, None, None


def upload_to_social_media(
    image_paths: list[Path],
    config: dict,
    upload_now: bool,
    scheduled_date_iso: Optional[str],
    timezone_str: Optional[str],
    user: str = UPLOAD_POST_USER,
) -> dict:
    """
    Perform upload via Upload-Post API. Handles retries and rate limits.
    Returns result dict with success, results per platform, and any error info.
    """
    # Instagram carousel: cap at 10 images
    paths_to_upload = image_paths[:INSTAGRAM_CAROUSEL_MAX] if image_paths else []

    headers = {"Authorization": f"Apikey {API_KEY}"}
    platforms = config.get("platforms", ["tiktok", "instagram"])

    files = []
    for p in paths_to_upload:
        files.append(("photos[]", (p.name, open(p, "rb"), "application/octet-stream")))

    # Form data: platform[] must be sent as multiple fields
    data = [
        ("user", user),
        ("title", config.get("title", "My Post")),
        ("privacy_level", "PUBLIC_TO_EVERYONE"),
    ]
    for plat in platforms:
        data.append(("platform[]", plat))
    if config.get("description"):
        data.append(("description", config["description"]))
    if config.get("tiktok_title"):
        data.append(("tiktok_title", config["tiktok_title"]))
    if config.get("instagram_title"):
        data.append(("instagram_title", config["instagram_title"]))
    if config.get("tiktok_song"):
        data.append(("tiktok_song", config["tiktok_song"]))
    if "instagram" in platforms:
        data.append(("media_type", "REELS"))
    if not upload_now and scheduled_date_iso and timezone_str:
        data.append(("scheduled_date", scheduled_date_iso))
        data.append(("timezone", timezone_str))

    result = {"success": False, "results": {}, "error": None, "request_id": None, "job_id": None}
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            # Re-open files for retries
            if attempt > 0:
                for _, (_, fh, _) in files:
                    if hasattr(fh, "close"):
                        fh.close()
                files = []
                for p in paths_to_upload:
                    files.append(("photos[]", (p.name, open(p, "rb"), "application/octet-stream")))

            print("\nUploading...", end=" ", flush=True)
            resp = requests.post(
                API_UPLOAD_URL,
                headers=headers,
                data=data,
                files=files,
                timeout=120,
            )

            # Rate limit
            if resp.status_code == 429:
                result["error"] = resp.text
                try:
                    j = resp.json()
                    usage = j.get("usage", {})
                    print(f"\nRate limit (429). Usage: {usage.get('count')}/{usage.get('limit')}. Retrying after delay...")
                except Exception:
                    print("\nRate limit (429). Retrying after delay...")
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                last_exception = None
                continue

            resp.raise_for_status()
            body = resp.json()

            if resp.status_code == 202:
                result["success"] = True
                result["job_id"] = body.get("job_id")
                result["scheduled_date"] = body.get("scheduled_date")
                result["message"] = "Scheduled successfully."
                break

            result["success"] = body.get("success", False)
            result["results"] = body.get("results", {})
            result["request_id"] = body.get("request_id")
            result["message"] = body.get("message", "")
            break

        except requests.RequestException as e:
            last_exception = e
            print(f"\nNetwork error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
        finally:
            for _, (_, fh, _) in files:
                if hasattr(fh, "close"):
                    try:
                        fh.close()
                    except Exception:
                        pass
    else:
        if last_exception:
            result["error"] = str(last_exception)

    return result


def save_upload_history(entry: dict) -> None:
    """Append upload result to upload_history.json."""
    history = []
    if os.path.isfile(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, IOError):
            history = []
    history.append({**entry, "timestamp": datetime.utcnow().isoformat() + "Z"})
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save history: {e}")


def run_single_upload(user: str) -> bool:
    """Run one upload flow. Returns True to continue batch, False to exit."""
    folder_path = get_folder_path()
    if not folder_path:
        return False

    image_paths = get_image_files(folder_path)
    if not image_paths:
        print("No image files (.jpg, .jpeg, .png, .webp) found in that folder.")
        return True  # allow batch to continue

    display_folder_contents(image_paths)
    confirm = input("\nProceed with these images? (y/n): ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Cancelled.")
        return True

    config = get_upload_config(len(image_paths))
    upload_now, scheduled_iso, timezone_str = schedule_or_now()

    print("\nUploading to " + " and ".join(config["platforms"]) + "...")
    upload_result = upload_to_social_media(
        image_paths,
        config,
        upload_now=upload_now,
        scheduled_date_iso=scheduled_iso,
        timezone_str=timezone_str,
        user=user,
    )

    # Display results
    if upload_result.get("job_id"):
        print(f"✓ Scheduled. job_id: {upload_result['job_id']}")
        if upload_result.get("scheduled_date"):
            print(f"  Scheduled for: {upload_result['scheduled_date']}")
    elif upload_result.get("request_id"):
        print(f"✓ Upload running in background. request_id: {upload_result['request_id']}")
        print("  Check status: GET /api/uploadposts/status?request_id=" + upload_result["request_id"])
    else:
        for platform, plat_result in upload_result.get("results", {}).items():
            if isinstance(plat_result, dict):
                if plat_result.get("success"):
                    url = plat_result.get("url", "N/A")
                    print(f"✓ {platform.capitalize()}: Success! {url}")
                else:
                    err = plat_result.get("error", "Unknown error")
                    print(f"✗ {platform.capitalize()}: Failed - {err}")
            else:
                print(f"  {platform}: {plat_result}")

    if upload_result.get("error"):
        print(f"Error: {upload_result['error']}")

    print("\nUpload complete!")

    save_upload_history({
        "folder": str(folder_path),
        "image_count": len(image_paths),
        "platforms": config.get("platforms", []),
        "scheduled": not upload_now,
        "success": upload_result.get("success"),
        "results": upload_result.get("results", {}),
        "job_id": upload_result.get("job_id"),
        "request_id": upload_result.get("request_id"),
        "error": upload_result.get("error"),
    })
    return True


def main() -> None:
    """Main interactive flow with optional batch mode."""
    print("=== Social Media Auto-Upload Tool ===\n")
    if USE_SANDBOX:
        print("(SANDBOX mode — posts go to sandbox, not production)\n")

    if not validate_api_key():
        sys.exit(1)

    user = os.environ.get("UPLOAD_POST_USER", UPLOAD_POST_USER)
    if user == "mybrand":
        custom = input("Upload-Post user/profile name (press Enter for 'mybrand'): ").strip()
        if custom:
            user = custom

    while True:
        if not run_single_upload(user):
            break
        again = input("\nUpload another folder? (y/n): ").strip().lower()
        if again not in ("y", "yes"):
            print("Done.")
            break


if __name__ == "__main__":
    main()
