#!/usr/bin/env python3
"""
Prepare images for TikTok Content Posting API via GitHub Pages.

- Copies images from tiktok_output/<folder> into the recipe-names repo under the same folder name.
- Pushes to GitHub so they're available at https://conor9656.github.io/recipe-names/<folder>/.
- Builds the public URLs for TikTok's photo_images (PULL_FROM_URL).
- Optionally converts PNG to JPEG (TikTok photo API supports WebP and JPEG only).

Usage:
  1. Set GITHUB_TOKEN env var (optional) for push, or have git credentials configured.
  2. Run this script and enter the folder name (e.g. 17).
  3. Script clones repo if needed, copies images, commits, and pushes.
  4. Use the printed URLs in the TikTok Content Posting API.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# Optional: convert PNG to JPEG for TikTok (TikTok photo API accepts WebP, JPEG only)
try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
BASE_DIRECTORY = os.environ.get(
    "UPLOAD_BASE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiktok_output"),
)
# GitHub Pages URL and repo for conor9656/recipe-images
GITHUB_PAGES_BASE_URL = "https://conor9656.github.io/recipe-names/"
GITHUB_REPO_URL = "https://github.com/conor9656/recipe-names/"
REPO_CLONE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recipe-names-repo")

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
# TikTok photo API: WebP, JPEG only (no PNG)
TIKTOK_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".webp"}


def get_image_files(folder_path: Path) -> list[Path]:
    """Return image paths sorted by filename."""
    files = [
        p for p in folder_path.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]
    return sorted(files, key=lambda x: x.name)


def copy_or_convert_to_jpeg(src: Path, dest_dir: Path) -> Path:
    """
    Copy image to dest_dir. If PNG and Pillow available, convert to JPEG for TikTok.
    Returns path to the file that was written (dest_dir/filename with correct extension).
    """
    dest_dir = Path(dest_dir)
    if src.suffix.lower() in TIKTOK_PHOTO_EXTENSIONS:
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        return dest
    if src.suffix.lower() == ".png" and HAS_PILLOW:
        base = src.stem
        dest = dest_dir / f"{base}.jpg"
        img = Image.open(src)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(dest, "JPEG", quality=92)
        return dest
    # PNG but no Pillow: copy anyway (TikTok may reject; user can convert manually)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return dest


def build_urls(base_url: str, filenames: list[str], subfolder: str) -> list[str]:
    """Build full GitHub Pages URLs. base_url should not end with /."""
    base = base_url.rstrip("/")
    prefix = f"{base}/{subfolder}" if subfolder else base
    prefix = prefix.rstrip("/") + "/"
    return [f"{prefix}{name}" for name in filenames]


def ensure_repo_cloned() -> Optional[Path]:
    """Clone repo to REPO_CLONE_DIR if not present; return repo path or None on failure."""
    repo_path = Path(REPO_CLONE_DIR)
    if (repo_path / ".git").is_dir():
        try:
            subprocess.run(
                ["git", "pull"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return repo_path
    repo_path.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("GITHUB_TOKEN")
    clone_url = GITHUB_REPO_URL
    if token:
        # HTTPS with token for private or to avoid auth prompts
        clone_url = f"https://{token}@github.com/conor9656/recipe-names.git"
    try:
        subprocess.run(
            ["git", "clone", clone_url, repo_path],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return repo_path
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"Could not clone repo: {e}")
        if not token:
            print("Tip: Set GITHUB_TOKEN env var for HTTPS clone/push.")
        return None


def git_push(repo_path: Path, folder_name: str) -> bool:
    """Run git add, commit, push. Returns True on success."""
    token = os.environ.get("GITHUB_TOKEN")
    push_url = GITHUB_REPO_URL
    if token:
        push_url = f"https://{token}@github.com/conor9656/recipe-names.git"
    try:
        subprocess.run(
            ["git", "add", "."],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Add images for folder {folder_name}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        # Push (may need origin/main or origin/master)
        for branch in ("main", "master"):
            r = subprocess.run(
                ["git", "push", push_url, branch],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode == 0:
                return True
        print("Git push failed. Check GITHUB_TOKEN or git credentials.")
        if not token:
            print("Tip: Set GITHUB_TOKEN env var for push.")
        return False
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"Git error: {e}")
        return False


def main() -> None:
    print("=== GitHub Pages → TikTok photo URLs ===\n")
    print(f"Repo: {GITHUB_PAGES_BASE_URL}\n")

    base = Path(BASE_DIRECTORY)
    if not base.is_dir():
        print(f"Base directory not found: {base}")
        return

    print(f"Base directory: {base.resolve()}\n")
    folder_name = input("Enter folder name (e.g. 17): ").strip()
    if not folder_name:
        print("No folder entered.")
        return

    folder_path = base / folder_name
    if not folder_path.is_dir():
        folder_path = Path(folder_name)
    if not folder_path.is_dir():
        print(f"Folder not found: {folder_path}")
        return

    images = get_image_files(folder_path)
    if not images:
        print("No images (.jpg, .jpeg, .png, .webp) in that folder.")
        return

    print(f"Found {len(images)} image(s):")
    for i, p in enumerate(images, 1):
        print(f"  {i}. {p.name}")
    print()

    # Subfolder in repo = same as folder name (e.g. 17)
    subfolder = folder_name

    # Clone repo if needed
    repo_path = ensure_repo_cloned()
    if not repo_path:
        print("Falling back to local export only (no push).")
        repo_path = Path(REPO_CLONE_DIR)
        repo_path.mkdir(parents=True, exist_ok=True)

    out_dir = repo_path / subfolder
    out_dir.mkdir(parents=True, exist_ok=True)

    # Clear existing files in that subfolder so we don't leave old images
    for f in out_dir.iterdir():
        if f.is_file():
            f.unlink()

    dest_filenames = []
    png_warn = False
    for src in images:
        dest_path = copy_or_convert_to_jpeg(src, out_dir)
        dest_filenames.append(dest_path.name)
        if src.suffix.lower() == ".png" and not HAS_PILLOW:
            png_warn = True

    urls = build_urls(GITHUB_PAGES_BASE_URL, dest_filenames, subfolder)

    # Push to GitHub (only if we have a real clone with .git)
    if (Path(REPO_CLONE_DIR) / ".git").is_dir():
        print("Pushing to GitHub...")
        if git_push(Path(REPO_CLONE_DIR), folder_name):
            print("Push successful.\n")
        else:
            print("Push failed. Files are in", out_dir.resolve(), "\n")
    else:
        print(f"Files written to: {out_dir.resolve()}\n")

    print("--- URLs for TikTok ---\n")
    print("Public URLs (use these in TikTok photo_images):\n")
    for u in urls:
        print(u)
    print("\nJSON array for TikTok API (photo_images):\n")
    print(json_array(urls))

    if png_warn:
        print("\nNote: Some source files were PNG. TikTok photo API supports WebP and JPEG only.")
        print("Install Pillow (pip install Pillow) to auto-convert PNG to JPEG, or convert manually.")
    if not HAS_PILLOW and any(p.suffix.lower() == ".png" for p in images):
        print("\nTip: pip install Pillow to auto-convert PNG → JPEG for TikTok.")

    print("\nNext steps:")
    print("1. Wait ~1 min for GitHub Pages to update, then use the URLs above in the TikTok API.")
    print("2. POST /v2/post/publish/content/init/ with source_info.source = PULL_FROM_URL")


def json_array(urls: list[str]) -> str:
    """Pretty-print a JSON array of URLs."""
    import json
    return json.dumps(urls, indent=2)


if __name__ == "__main__":
    main()
