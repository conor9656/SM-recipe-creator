# Agent / contributor guide — recipe scraper

## Environment setup (commands)

Use **Python 3.10+** (3.13 is fine). From the repo root:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -U pip
pip install -r requirements.txt
```

Optional: copy `.env.example` to `.env` and fill secrets (never commit `.env`). See **Secrets** below.

## Secrets (`.env`)

| Variable | Used by |
|----------|---------|
| `OPENAI_API_KEY` | AI instruction summarization in `tiktok_recipe_images.py` |
| `SEGMIND_API_KEY` | Optional; Segmind Kimi for summarization |
| `GITHUB_TOKEN` | `tiktok_recipe_to_tiktok.py` — push to `recipe-names` GitHub repo |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REDIRECT_URI` | `tiktok_oauth_token.py` |
| `UPLOAD_POST_API_KEY` | `social_media_upload.py` (Upload-Post API) |

`tiktok_tokens.json` is produced by `tiktok_oauth_token.py` and is gitignored.

## What each script does

| Script | Purpose |
|--------|---------|
| `tiktok_recipe_images.py` | Scrape recipe URLs → meal images + recipe cards + opening image; batched into `Part_1`, `Part_2` under `tiktok_output/<run>/`. Entry: prompts for title + txt vs AI URLs. |
| `tiktok_recipe_to_tiktok.py` | **Main pipeline**: load URLs from `URL_FILE` → generate images → push each part to GitHub Pages → post each part to TikTok (Content Posting API). Prompts for TikTok title + description. |
| `tiktok_oauth_token.py` | OAuth v2 desktop flow → writes `tiktok_tokens.json`. |
| `tiktok_post_photo.py` | Standalone TikTok photo post (single URL or folder + base URL). |
| `github_pages_tiktok.py` | Standalone: copy a folder to `recipe-names` repo, push, print URLs. |
| `social_media_upload.py` | Upload images via **Upload-Post** API (TikTok/Instagram), not official TikTok API. |
| `scraper.py` | General recipe scraping utility. |
| `recipe_url_extractor.py` | Extract recipe URLs. |
| `tiktok_recipe_text.py` | Text-related recipe tooling (see file docstring). |
| `ingredient_enricher.py` | Ingredient enrichment (separate `requirements_ingredient_enricher.txt` if minimal install). |

**Config** in `tiktok_recipe_images.py`: `URL_FILE`, `OUTPUT_DIR`, `RECIPES_PER_PART`, paths to `background.png`, fonts, etc.

## Coding conventions for this repo

- **Minimal diffs**: change only what the task needs; match existing style (imports, logging, typing).
- **Secrets**: never hardcode API keys; use `.env` / env vars; keep `tiktok_tokens.json` and `.env` out of git.
- **TikTok posting**: photo posts use `PULL_FROM_URL`; images must be on a **verified** domain; pipeline uses GitHub Pages + waits until URLs return HTTP 200. Unaudited apps use `privacy_level: SELF_ONLY`.
- **Image URLs**: local PNGs map to `.jpg` URLs when matching `github_pages_tiktok` conversion.
- **Do not** add large unrelated refactors or unsolicited markdown docs unless the user asks.

## Typical run order (full TikTok flow)

1. Put recipe URLs in `URL_FILE` (e.g. `meals-this-week.txt` — check `tiktok_recipe_images.py` for the constant).
2. `python tiktok_oauth_token.py` once (or refresh tokens) → `tiktok_tokens.json`.
3. `python tiktok_recipe_to_tiktok.py` — generates images, pushes GitHub, posts TikTok.

Or run `tiktok_recipe_images.py` alone for images only; use `github_pages_tiktok.py` + `tiktok_post_photo.py` for manual steps.
