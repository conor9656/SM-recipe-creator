# TikTok access token and redirect URI

You need a **user access token** (and optionally **refresh token**) to call the Content Posting API. TikTok uses OAuth: the user signs in in the browser and your app gets a `code`, then exchanges it for an `access_token`.

---

## Sandbox vs Production for Content Posting

**For posting photos (or videos) to TikTok, you must use Production, not Sandbox.**

From [TikTok’s Add a Sandbox](https://developers.tiktok.com/doc/add-a-sandbox):

> **Sandbox mode does not offer access to Content Posting API for public videos** or Data Portability API.

So:

- **Sandbox**: Good for testing Login Kit and other products; **cannot** be used for Content Posting (no public photo/video posts).
- **Production**: Required for the Content Posting API. Use your app in **Production** (Draft is fine). After your app is approved and Live, you can post; until then, posts from “unaudited” apps may be restricted to private viewing.

**What to do:** Switch your app to **Production** in the TikTok for Developers dashboard, keep your URL prefix verified there, then get an access token using Production credentials (client key/secret). Use the script below or the manual flow.

---

## What is the redirect URI?

The **redirect URI** is the URL TikTok sends the user **back to** after they approve your app. Your app must:

1. Send the user to TikTok’s authorize page (with `redirect_uri` in the URL).
2. **Listen on that same URL** (e.g. a local web server) so when TikTok redirects the user with `?code=...`, your app can read the `code` and exchange it for an access token.

So the redirect URI is **your** URL that can receive that redirect. For a desktop/CLI app it has to be on your machine.

### Rules for desktop (from [Login Kit for Desktop](https://developers.tiktok.com/doc/login-kit-desktop))

- **Host:** Only `localhost` or `127.0.0.1`.
- **Port:** Must be present; a fixed port (e.g. `8080`) or wildcard `*` is allowed.
- **Protocol:** `http` or `https`.
- **Path:** Any static path, e.g. `/callback/` (no query or fragment in the *registered* URI).

**Good examples:**

- `http://localhost:8080/callback/`
- `http://127.0.0.1:8080/callback/`
- `http://127.0.0.1:*/callback/` (wildcard port; useful if the port is chosen at runtime)

**Wrong:**

- `https://conor9656.github.io/recipe-images/` — not localhost; TikTok won’t redirect users to your GitHub site for this flow.
- `http://localhost/callback/` — no port (desktop requires a port).

### What to put in the TikTok app

1. Go to [TikTok for Developers](https://developers.tiktok.com/) → **Manage apps** → your app.
2. Ensure you’re in **Production** (toggle at top).
3. Open **Login Kit** (or the product where Redirect URIs are configured). For **Desktop**, add a redirect URI that **exactly** matches what your script uses, e.g.:
   - `http://localhost:8080/callback/`
4. Save.

The value in the app must match the `redirect_uri` you use in the authorize URL and the one your local server listens on (e.g. `http://localhost:8080/callback/`).

---

## Getting an access token

**Option A – Use the script (recommended)**

1. In **Production**, copy your app’s **Client key** and **Client secret**.
2. Add to `.env` (or set env vars):
   ```env
   TIKTOK_CLIENT_KEY=your_client_key
   TIKTOK_CLIENT_SECRET=your_client_secret
   ```
3. In the app’s Login Kit → Desktop, add redirect URI: `http://localhost:8080/callback/`
4. Run:
   ```bash
   python tiktok_get_token.py
   ```
5. A browser will open; log in to TikTok and approve. The script will capture the `code`, exchange it for a token, and save it.

**Option B – Manual**

1. Open the authorize URL in a browser (with your `client_key`, `scope=video.publish`, `redirect_uri`, `state`, and for desktop, `code_challenge` + `code_challenge_method=S256`).  
   See [OAuth User Access Token Management](https://developers.tiktok.com/doc/oauth-user-access-token-management) and [Login Kit for Desktop](https://developers.tiktok.com/doc/login-kit-desktop) for parameters.
2. After you approve, the browser will redirect to your `redirect_uri` with `?code=...`. Copy the `code` from the URL.
3. Exchange the code for a token:  
   `POST https://open.tiktokapis.com/v2/oauth/token/`  
   with `client_key`, `client_secret`, `code`, `grant_type=authorization_code`, `redirect_uri` (same as in step 1), and for desktop, `code_verifier`.
4. Store `access_token` and `refresh_token` (and optionally `open_id`) for use in the Content Posting API.

---

## Summary

| Question | Answer |
|----------|--------|
| Sandbox or Production for posting? | **Production.** Sandbox does not support Content Posting for public content. |
| What should the redirect URI be? | A **localhost** URL with a port, e.g. `http://localhost:8080/callback/`, registered in your app and used by your local server. |
| Where do I set it? | In the app (Production) → Login Kit → Desktop → Redirect URIs. Add the exact URI your script uses. |
