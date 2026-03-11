#!/usr/bin/env python3
"""
Combined pipeline: Recipe images → GitHub Pages → TikTok post.

1. Asks for TikTok video title (Part 1, Part 2, … added automatically) and description.
2. Loads recipe URLs from the txt file (default).
3. Generates recipe card and opening images (batched into parts).
4. Pushes each part to GitHub, then posts each part to TikTok with the given title and description.

Requires: tiktok_tokens.json (run tiktok_oauth_token.py once), GITHUB_TOKEN in .env for push.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import image generation
from tiktok_recipe_images import (
    URL_FILE,
    run_image_generation,
)

# GitHub Pages config (from github_pages_tiktok)
GITHUB_PAGES_BASE_URL = "https://conor9656.github.io/recipe-names/"
GITHUB_REPO_URL = "https://github.com/conor9656/recipe-names/"
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_CLONE_DIR = SCRIPT_DIR / "recipe-names-repo"

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
TIKTOK_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".webp"}
MAX_PHOTOS_PER_POST = 35

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

# TikTok post (from tiktok_post_photo)
import json
import requests
TOKENS_FILE = SCRIPT_DIR / "tiktok_tokens.json"
CONTENT_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/content/init/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


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


def copy_or_convert_to_jpeg(src: Path, dest_dir: Path) -> Path:
    """Copy image to dest_dir; convert PNG to JPEG for TikTok if Pillow available."""
    dest_dir = Path(dest_dir)
    if src.suffix.lower() in TIKTOK_PHOTO_EXTENSIONS:
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        return dest
    if src.suffix.lower() == ".png" and HAS_PILLOW:
        dest = dest_dir / f"{src.stem}.jpg"
        img = Image.open(src)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(dest, "JPEG", quality=92)
        return dest
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return dest


def ensure_repo_cloned() -> Path | None:
    """Clone repo to REPO_CLONE_DIR if not present; return repo path or None."""
    repo_path = Path(REPO_CLONE_DIR)
    if (repo_path / ".git").is_dir():
        try:
            subprocess.run(["git", "pull"], cwd=repo_path, capture_output=True, text=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return repo_path
    repo_path.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("GITHUB_TOKEN")
    clone_url = f"https://{token}@github.com/conor9656/recipe-names.git" if token else GITHUB_REPO_URL
    try:
        subprocess.run(
            ["git", "clone", clone_url, str(repo_path)],
            check=True, capture_output=True, text=True, timeout=60,
        )
        return repo_path
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"Could not clone repo: {e}")
        return None


def git_push(repo_path: Path, commit_message: str) -> bool:
    """Run git add, commit, push. Returns True on success."""
    token = os.environ.get("GITHUB_TOKEN")
    push_url = f"https://{token}@github.com/conor9656/recipe-names.git" if token else GITHUB_REPO_URL
    try:
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", commit_message], cwd=repo_path, capture_output=True, text=True)
        for branch in ("main", "master"):
            r = subprocess.run(["git", "push", push_url, branch], cwd=repo_path, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                return True
        return False
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def push_part_to_github(part_dir: Path, subfolder_name: str) -> str | None:
    """
    Copy images from part_dir to repo/subfolder_name (PNG→JPEG), push to GitHub.
    Returns base URL for the part (e.g. https://conor9656.github.io/recipe-names/17_Part_1) or None on failure.
    """
    repo_path = ensure_repo_cloned()
    if not repo_path:
        return None
    images = get_image_files(part_dir)
    if not images:
        return None
    out_dir = repo_path / subfolder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.iterdir():
        if f.is_file():
            f.unlink()
    for src in images:
        copy_or_convert_to_jpeg(src, out_dir)
    if git_push(repo_path, f"Add images for {subfolder_name}"):
        return f"{GITHUB_PAGES_BASE_URL.rstrip('/')}/{subfolder_name}"
    return None


def load_tokens() -> dict | None:
    """Load tokens from tiktok_tokens.json."""
    if not TOKENS_FILE.is_file():
        return None
    with open(TOKENS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if data.get("access_token") else None


def local_path_to_hosted_url(base_url: str, local_path: Path) -> str:
    """Build URL for a file as hosted (PNG→.jpg to match conversion)."""
    base_url = base_url.rstrip("/")
    name = f"{local_path.stem}.jpg" if local_path.suffix.lower() == ".png" else local_path.name
    return f"{base_url}/{name}"


def post_part_to_tiktok(
    access_token: str,
    part_dir: Path,
    base_url: str,
    title: str,
    description: str = "",
    privacy_level: str = "SELF_ONLY",
    log_urls: bool = True,
) -> dict:
    """Post all images in part_dir to TikTok using PULL_FROM_URL (base_url = hosted part URL)."""
    images = get_image_files(part_dir)[:MAX_PHOTOS_PER_POST]
    photo_urls = [local_path_to_hosted_url(base_url, p) for p in images]
    if not photo_urls:
        return {"error": {"code": "invalid_param", "message": "No images"}}
    if log_urls:
        print(f"  [DEBUG] base_url sent to TikTok: {base_url}")
        print(f"  [DEBUG] photo_urls ({len(photo_urls)}):")
        for u in photo_urls:
            print(f"    {u}")
    body = {
        "post_info": {
            "title": title[:90],
            "description": description[:4000],
            "privacy_level": privacy_level,
            "disable_comment": False,
            "auto_add_music": True,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "photo_cover_index": 0,
            "photo_images": photo_urls,
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


def fetch_post_status(access_token: str, publish_id: str) -> dict:
    """Check post status by publish_id (PROCESSING, PUBLISHED, FAILED)."""
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


def main() -> None:
    print("=== TikTok Recipe → GitHub Pages → TikTok Post ===\n")

    # ----- Upload section: title and description for TikTok -----
    video_title = input("TikTok video title (Part 1, Part 2, etc. will be added automatically): ").strip()
    if not video_title:
        video_title = "Recipe cards"
    description = input("Description for the posts (with hashtags): ").strip()

    # ----- Load recipe URLs from txt file (default) -----
    if not os.path.isfile(URL_FILE):
        print(f"No URL file found: {URL_FILE}")
        return
    urls = []
    with open(URL_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    if not urls:
        print(f"No URLs found in {URL_FILE}")
        return
    print(f"Loaded {len(urls)} recipe URL(s) from {URL_FILE}\n")

    # ----- Step 1: Generate images -----
    print("\n--- Step 1: Generating recipe images ---\n")
    run_dir = run_image_generation(video_title, urls)
    run_dir = Path(run_dir)
    run_number = run_dir.name
    print(f"Images saved to: {run_dir.resolve()}\n")

    # ----- Step 2 & 3: Push each part to GitHub, then post to TikTok -----
    tokens = load_tokens()
    if not tokens:
        print("TikTok tokens not found. Run tiktok_oauth_token.py first, then re-run this script to post.")
        print("Images are ready in:", run_dir.resolve())
        return

    access_token = tokens["access_token"]
    part_dirs = sorted([p for p in run_dir.iterdir() if p.is_dir() and p.name.startswith("Part_")])
    if not part_dirs:
        print("No Part_* folders found in run directory.")
        return

    print("--- Step 2 & 3: Push to GitHub and post to TikTok ---\n")
    print("Using privacy_level: SELF_ONLY (required for unaudited apps).")
    print("Posts will only be visible to you (Only me) until your app is audited.\n")
    for part_dir in part_dirs:
        part_name = part_dir.name  # Part_1, Part_2, ...
        subfolder_name = f"{run_number}_{part_name}"  # e.g. 17_Part_1
        part_title = f"{video_title} ({part_name.replace('_', ' ')})"

        print(f"Pushing {part_name} to GitHub...")
        base_url = push_part_to_github(part_dir, subfolder_name)
        if not base_url:
            print(f"  Push failed for {part_name}. Skipping TikTok post for this part.")
            continue
        print(f"  URL: {base_url}")

        # GitHub Pages can take 1–2 min to deploy after push; wait until first image is reachable (or timeout)
        images_pre = get_image_files(part_dir)[:1]
        if not images_pre:
            print("  [WARN] No images in part; skipping TikTok post.")
            continue
        first_url = local_path_to_hosted_url(base_url, images_pre[0])
        print("  Waiting for GitHub Pages to serve images (polling every 15s, max 2 min)...")
        page_ready = False
        for attempt in range(9):  # 30s + 8*15s = 150s max
            if attempt == 0:
                time.sleep(30)
            else:
                time.sleep(15)
            try:
                r = requests.get(first_url, timeout=15, allow_redirects=True, stream=True)
                r.close()
                if r.status_code == 200 and r.url == first_url:
                    waited = 30 + (attempt * 15) if attempt > 0 else 30
                    print(f"  [OK] First image reachable after {waited}s.")
                    page_ready = True
                    break
                if r.status_code == 200 and r.url != first_url:
                    print(f"  [WARN] URL redirects; TikTok may not follow. Proceeding anyway.")
                    page_ready = True
                    break
            except Exception as e:
                print(f"  Poll attempt {attempt + 1}: {e}")
        if not page_ready:
            print(f"  [ERROR] First image still 404 after ~2 min: {first_url}")
            print("  Skip TikTok for this part and try again in a few minutes, or open the URL in a browser to confirm.")
            print()
            continue

        print(f"  Posting {part_name} to TikTok (privacy: SELF_ONLY)...")
        result = post_part_to_tiktok(
            access_token,
            part_dir,
            base_url,
            title=part_title,
            description=description,
            privacy_level="SELF_ONLY",
        )
        status_code = result.get("_status_code", 0)
        err = result.get("error", {})
        code = err.get("code", "")

        if status_code != 200 or code != "ok":
            print(f"  [ERROR] Post init failed. HTTP {status_code}, code: {code}")
            print(f"  message: {err.get('message', '')}")
            print(f"  full error: {json.dumps(err, indent=2)}")
            print()
            continue

        publish_id = result.get("data", {}).get("publish_id")
        print(f"  Init OK. publish_id: {publish_id}")

        # TikTok processes the post asynchronously; check status to see if it actually published or failed
        print("  Checking post status (async processing)...")
        time.sleep(5)
        status_result = fetch_post_status(access_token, publish_id)
        status_err = status_result.get("error", {})
        status_data = status_result.get("data", {})

        if status_err.get("code") != "ok":
            print(f"  [WARN] Status check error: {status_err}")

        post_status = status_data.get("status", "")
        fail_reason = status_data.get("fail_reason", "")

        if post_status == "PUBLISHED":
            print(f"  [OK] Post is live (SELF_ONLY: visible only to you in TikTok).")
        elif post_status == "PROCESSING":
            print(f"  [INFO] Still processing. Check again in the TikTok app (Profile → Only me) in a minute.")
        elif post_status == "FAILED":
            print(f"  [ERROR] Post failed after upload. fail_reason: {fail_reason}")
            if "photo_pull_failed" in fail_reason:
                print("  → TikTok could not fetch image URLs. Check that GitHub Pages URLs are public and JPEG/WebP.")
            print(f"  full status data: {json.dumps(status_data, indent=2)}")
        else:
            print(f"  [INFO] status={post_status}, fail_reason={fail_reason or '(none)'}")
            if status_data:
                print(f"  raw: {json.dumps(status_data, indent=2)}")
        print()

    print("Done. Unaudited apps: posts are SELF_ONLY (Only me) until your client is audited.")


if __name__ == "__main__":
    main()
