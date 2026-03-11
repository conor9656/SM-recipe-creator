#!/usr/bin/env python3
"""
Post one or more photos to TikTok using the Content Posting API.

Uses the access_token from tiktok_tokens.json (from tiktok_oauth_token.py).
Images must be at public URLs from a domain verified in the TikTok Developer Portal.

Usage:
  Single image:
    python tiktok_post_photo.py "https://example.com/image.jpg" "My title"
  Folder (one post with all images; images must already be hosted at base_url):
    python tiktok_post_photo.py "tiktok_output/17" "https://conor9656.github.io/recipe-names/17" "Title"
  Interactive:
    python tiktok_post_photo.py
"""

import json
import os
import sys
from pathlib import Path

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKENS_FILE = os.path.join(SCRIPT_DIR, "tiktok_tokens.json")
CONTENT_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/content/init/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PHOTOS_PER_POST = 35  # TikTok limit


def load_tokens():
    """Load access_token and open_id from tiktok_tokens.json."""
    if not os.path.isfile(TOKENS_FILE):
        print(f"Error: Token file not found: {TOKENS_FILE}")
        print("Run tiktok_oauth_token.py first to obtain tokens.")
        return None
    with open(TOKENS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    token = data.get("access_token")
    if not token:
        print("Error: access_token not found in token file.")
        return None
    return data


def query_creator_info(access_token: str) -> dict | None:
    """Get creator info including privacy_level_options."""
    resp = requests.post(
        CREATOR_INFO_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"Creator info failed ({resp.status_code}): {resp.text}")
        return None
    data = resp.json()
    if data.get("error", {}).get("code") != "ok":
        print("Creator info error:", data.get("error"))
        return None
    return data.get("data")


def get_image_files(folder_path: Path) -> list[Path]:
    """Return image paths in folder, sorted by filename."""
    folder_path = Path(folder_path)
    if not folder_path.is_dir():
        return []
    files = [
        p for p in folder_path.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]
    return sorted(files, key=lambda x: x.name)


def local_path_to_hosted_url(base_url: str, local_path: Path) -> str:
    """
    Build the URL for a file as hosted (e.g. on GitHub Pages).
    If you use github_pages_tiktok.py, it converts PNG→JPEG and saves as .jpg,
    so we use .jpg in the URL for local .png files to match. TikTok only accepts JPEG/WebP.
    """
    base_url = base_url.rstrip("/")
    if local_path.suffix.lower() == ".png":
        # github_pages_tiktok converts PNG to .jpg; TikTok doesn't accept PNG
        name = f"{local_path.stem}.jpg"
    else:
        name = local_path.name
    return f"{base_url}/{name}"


def post_photo(
    access_token: str,
    photo_urls: str | list[str],
    title: str = "",
    description: str = "",
    privacy_level: str = "SELF_ONLY",
    disable_comment: bool = False,
    auto_add_music: bool = True,
    photo_cover_index: int = 0,
) -> dict:
    """
    Post one or more photos via Content Posting API (PULL_FROM_URL).
    photo_urls: single URL string or list of URLs (max 35). All must be from verified domain.
    """
    urls = [photo_urls] if isinstance(photo_urls, str) else list(photo_urls)
    urls = urls[:MAX_PHOTOS_PER_POST]
    if not urls:
        return {"error": {"code": "invalid_param", "message": "At least one photo URL required"}}
    body = {
        "post_info": {
            "title": (title or "Photo post")[:90],
            "description": (description or "")[:4000],
            "privacy_level": privacy_level,
            "disable_comment": disable_comment,
            "auto_add_music": auto_add_music,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "photo_cover_index": min(photo_cover_index, len(urls) - 1),
            "photo_images": urls,
        },
        "post_mode": "DIRECT_POST",
        "media_type": "PHOTO",
    }
    resp = requests.post(
        CONTENT_INIT_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json=body,
        timeout=30,
    )
    result = resp.json()
    result["_status_code"] = resp.status_code
    return result


def fetch_status(access_token: str, publish_id: str) -> dict:
    """Check post status by publish_id."""
    resp = requests.post(
        STATUS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={"publish_id": publish_id},
        timeout=15,
    )
    return resp.json()


def main():
    tokens = load_tokens()
    if not tokens:
        sys.exit(1)
    access_token = tokens["access_token"]

    # Optional: get creator info for privacy options
    creator = query_creator_info(access_token)
    if creator:
        options = creator.get("privacy_level_options", ["PUBLIC_TO_EVERYONE", "SELF_ONLY"])
        print(f"Creator: {creator.get('creator_username', creator.get('creator_nickname', 'N/A'))}")
        print(f"Privacy options: {options}")
    else:
        options = ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"]

    photo_urls = None
    title = "Photo post"
    description = ""

    if len(sys.argv) >= 2:
        first = sys.argv[1].strip()
        folder_path = Path(first)
        if folder_path.is_dir():
            # Folder: argv[2]=base URL, argv[3]=title, argv[4]=description
            base_url = (sys.argv[2].strip() if len(sys.argv) >= 3 else "").rstrip("/")
            if not base_url:
                print("Error: For a folder, provide the base URL where images are hosted (e.g. https://conor9656.github.io/recipe-names/17)")
                sys.exit(1)
            images = get_image_files(folder_path)
            if not images:
                print(f"No images (.jpg, .jpeg, .png, .webp) in {folder_path}")
                sys.exit(1)
            # Use .jpg URL for local .png (matches github_pages_tiktok conversion; TikTok accepts only JPEG/WebP)
            photo_urls = [local_path_to_hosted_url(base_url, p) for p in images[:MAX_PHOTOS_PER_POST]]
            if len(images) > MAX_PHOTOS_PER_POST:
                print(f"Using first {MAX_PHOTOS_PER_POST} images (TikTok limit).")
            title = sys.argv[3].strip() if len(sys.argv) >= 4 else "Photo post"
            description = sys.argv[4].strip() if len(sys.argv) >= 5 else ""
            print(f"Posting {len(photo_urls)} image(s) from folder:")
            for u in photo_urls:
                print(f"  {u}")
        elif first.startswith("http://") or first.startswith("https://"):
            photo_urls = first
            title = sys.argv[2].strip() if len(sys.argv) >= 3 else title
            description = sys.argv[3].strip() if len(sys.argv) >= 4 else ""
        else:
            print(f"Error: Not a folder and not a URL: {first}")
            sys.exit(1)
    else:
        print("\nEnter a single image URL, or a local folder path to post all images in that folder.")
        print("(Folder images must already be hosted; use github_pages_tiktok.py first if needed.)\n")
        first = input("Image URL or folder path: ").strip()
        if not first:
            print("No input.")
            sys.exit(1)
        title = input("Title (optional, max 90 chars): ").strip() or title
        description = input("Description (optional, max 4000 chars): ").strip()
        folder_path = Path(first)
        if folder_path.is_dir():
            base_url = input("Base URL where these images are hosted (e.g. https://conor9656.github.io/recipe-names/17): ").strip().rstrip("/")
            if not base_url:
                print("Base URL required for folder upload.")
                sys.exit(1)
            images = get_image_files(folder_path)
            if not images:
                print(f"No images in {folder_path}")
                sys.exit(1)
            photo_urls = [local_path_to_hosted_url(base_url, p) for p in images[:MAX_PHOTOS_PER_POST]]
            print(f"Will post {len(photo_urls)} image(s).")
        else:
            photo_urls = first

    # Unaudited apps can only post with SELF_ONLY (TikTok blocks others with 403)
    privacy = "SELF_ONLY"
    if options and privacy not in options:
        privacy = options[-1]
    print(f"Using privacy_level: {privacy} (required for unaudited apps)")

    print("\nPosting to TikTok...")
    result = post_photo(
        access_token,
        photo_urls,
        title=title,
        description=description,
        privacy_level=privacy,
        auto_add_music=True,
    )

    status_code = result.get("_status_code", 0)
    err = result.get("error", {})
    code = err.get("code", "")
    msg = err.get("message", "")

    if status_code == 200 and code == "ok":
        publish_id = result.get("data", {}).get("publish_id")
        print(f"Success! publish_id: {publish_id}")
        print("Note: Unaudited apps post as private until your client is audited.")
        if publish_id:
            check = input("Check post status? (y/n): ").strip().lower()
            if check in ("y", "yes"):
                status_result = fetch_status(access_token, publish_id)
                print(json.dumps(status_result, indent=2))
                data = status_result.get("data", {})
                if data.get("status") == "FAILED" and data.get("fail_reason") == "photo_pull_failed":
                    print("\nphoto_pull_failed: TikTok could not fetch one or more image URLs.")
                    print("  • Use JPEG or WebP only (no PNG). This script uses .jpg URLs for .png files to match github_pages_tiktok.")
                    print("  • Re-run github_pages_tiktok.py for this folder, then post again so URLs point to the hosted .jpg files.")
        return

    print(f"Post failed (HTTP {status_code})")
    print(f"  code: {code}")
    print(f"  message: {msg}")
    if "url_ownership_unverified" in (code + msg):
        print("\nYour image URL domain is not verified. In TikTok Developer Portal:")
        print("  Add your app > Content Posting API > Verify the domain or URL prefix for the image URL.")
    if "photo_pull_failed" in (code + str(result)):
        print("\nphoto_pull_failed: TikTok could not fetch one or more image URLs.")
        print("  • Use JPEG or WebP only (no PNG). If you use github_pages_tiktok.py, it converts PNG→JPG.")
        print("  • URLs must not redirect (use final HTTPS URL).")
        print("  • Ensure each URL returns 200 and is publicly accessible.")
    print("\nFull response:", json.dumps({k: v for k, v in result.items() if k != "_status_code"}, indent=2))
    sys.exit(1)


if __name__ == "__main__":
    main()
