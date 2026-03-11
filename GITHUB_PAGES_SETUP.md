# GitHub Pages setup for TikTok Content Posting API

Use GitHub Pages to host your images for free so TikTok can pull them via **PULL_FROM_URL**. Follow these steps once; then use `github_pages_tiktok.py` each time you have a new folder of images.

---

## Do I need a TikTok app? Can I verify without one?

**You do need a TikTok for Developers app** to use PULL_FROM_URL. The API always runs in the context of an app (client key, OAuth, etc.), and URL verification is done *inside* that app—there is no way to verify a URL without having an app.

**Verifying your URL is not the same as “app review.”**

- **URL verification** = Prove you own a domain or URL prefix (e.g. your GitHub Pages URL). TikTok gives you a **signature file** to upload to your site; once that file is reachable at the URL they expect, the prefix is verified. You can do this while your app is still in **Draft** or **Sandbox**—no approval needed.
- **App review** = Submitting your app so it can go **Live** (e.g. so other users can authorize it, or so posts can be public). For posting, “unaudited” apps can still post, but TikTok may restrict visibility until the app is audited.

So: create an app → add the Content Posting API product → verify your GitHub Pages URL by adding TikTok’s signature file to your repo. No need to have the app fully “verified” or approved to complete URL verification.

If TikTok asks you to verify a **website** (e.g. “Web” or “Desktop” platform URL, Terms of Service, Privacy Policy), that’s part of app registration. You can use the **same** GitHub Pages repo as your app’s “official website”: add a simple `index.html` with your app name, a link to a Terms of Service page, and a link to a Privacy Policy page (each can be another file in the repo). Then verify that base URL (and any other required URLs) using the same signature-file process below.

---

## 1. Create a GitHub repo for your images

1. Go to [GitHub](https://github.com/new).
2. Create a **new repository** (e.g. `recipe-images`).
3. Leave it empty or add a README—you'll add images in the next steps.

---

## 2. Enable GitHub Pages

1. In the repo: **Settings** → **Pages** (left sidebar).
2. Under **Source**, choose **Deploy from a branch**.
3. Branch: **main** (or **master**), folder: **/ (root)**.
4. Click **Save**.
5. Your site will be at: `https://<your-username>.github.io/<repo-name>/`

Example: if your username is `jane` and repo is `recipe-images`, the base URL is:
`https://jane.github.io/recipe-images`

---

## 3. Verify URL ownership in TikTok for Developers

TikTok only accepts image URLs from a **verified** domain or URL prefix. Verification is done by placing a **signature file** TikTok gives you onto your site—no separate “app verification” or “website verification” is required to complete this step.

**Prerequisite:** You must have a [TikTok for Developers](https://developers.tiktok.com/) account and an **app** with the **Content Posting API** product added. If you don’t have an app yet, create one under [Manage apps](https://developers.tiktok.com/apps) → Connect an app, then add the Content Posting API product.

**Exact steps (URL prefix verification):**

1. Go to [TikTok for Developers](https://developers.tiktok.com/) → **Manage apps** → open your app.
2. At the **top** of the app page, click the **URL properties** button (not in the left sidebar).
3. Ensure you’re in **Production** mode (toggle at top), then click **Verify properties**.
4. Choose **Verify by URL prefix** (not Domain, for GitHub Pages).
5. Enter your **full GitHub Pages base URL with a trailing slash**, e.g.:
   - `https://jane.github.io/recipe-images/`
   - Must be **https**, and must end with `/`.
6. Click **Verify**. TikTok will show you a **signature file** to download (e.g. a `.txt` or similar) and the **exact path** where it must be reachable (e.g. `https://jane.github.io/recipe-images/abc123.txt`).
7. **Add that file to your GitHub repo** at the path they specify (e.g. put `abc123.txt` in the root of `recipe-images` so the URL is `https://jane.github.io/recipe-images/abc123.txt`). Commit and push.
8. Wait for GitHub Pages to update (about a minute), then in TikTok click **Verify** again (or refresh verification). Once it succeeds, all URLs under that prefix are accepted for `photo_images`.

If you use a **Domain** instead of URL prefix, TikTok will ask you to add a **DNS TXT record**; that only works if you control the domain’s DNS (e.g. a custom domain). For `username.github.io`, use **URL prefix** and the signature file method above.

---

## 4. Run the script and push images

1. From your project folder, run:
   ```bash
   python github_pages_tiktok.py
   ```
2. Enter the **folder name** (e.g. `17` for `tiktok_output/17`).
3. Enter your **GitHub Pages base URL** (e.g. `https://jane.github.io/recipe-images`).
4. Enter the **subfolder in the repo** for these images (e.g. `17` or `images/17`). Default is the folder name.
5. The script will:
   - Copy (and optionally convert PNG→JPEG) images into `github_pages_export/<subfolder>/`.
   - Print the **public URLs** and a **JSON array** for TikTok’s `photo_images`.

6. Push the export folder to your repo:
   - Copy everything inside `github_pages_export/` into your repo (e.g. so you have `17/00_opening.jpg`, … in the repo root).
   - Example (from your recipe-images repo clone):
     ```bash
     cd path\to\your\recipe-images-repo
     xcopy /E /I "C:\Users\User\recipe scraper\github_pages_export\*" .
     git add .
     git commit -m "Add images for TikTok"
     git push
     ```
   - Or drag the contents of `github_pages_export` into your repo folder in File Explorer, then commit and push.

---

## 5. Use the URLs in the TikTok API

After the push, wait a minute so GitHub Pages updates. Then use the printed URLs in the [TikTok Photo Post API](https://developers.tiktok.com/doc/content-posting-api-reference-photo-post):

- **Endpoint:** `POST https://open.tiktokapis.com/v2/post/publish/content/init/`
- **Headers:** `Authorization: Bearer <access_token>`, `Content-Type: application/json`
- **Body (minimal):**
  ```json
  {
    "media_type": "PHOTO",
    "post_mode": "DIRECT_POST",
    "post_info": {
      "title": "Your caption here",
      "privacy_level": "PUBLIC_TO_EVERYONE"
    },
    "source_info": {
      "source": "PULL_FROM_URL",
      "photo_images": [
        "https://jane.github.io/recipe-images/17/00_opening.jpg",
        "https://jane.github.io/recipe-images/17/chicken-cacciatore_meal.jpg"
      ],
      "photo_cover_index": 0
    }
  }
  ```

`photo_cover_index` is the index (from 0) of the image to use as the cover. Order of `photo_images` must match the order you want in the slideshow.

---

## Notes

- **TikTok photo formats:** Only **WebP** and **JPEG**. The script can convert PNG→JPEG if Pillow is installed (`pip install Pillow`).
- **Verification:** If you get `url_ownership_unverified`, double-check the URL prefix in TikTok (with trailing `/`) and that the verification step is complete.
- **Rate limits:** TikTok allows 6 requests per minute per user for this endpoint.
