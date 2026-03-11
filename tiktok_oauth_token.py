#!/usr/bin/env python3
"""
TikTok OAuth v2 – get user access token for Content Posting API.

Uses client_key and client_secret from .env, opens the authorize URL in your
browser, then exchanges the code for access_token and refresh_token.
Tokens are saved to tiktok_tokens.json (add this file to .gitignore).

For Desktop: use a redirect URI like http://localhost:8080/callback (with a port)
and add it under "Redirect URI for Desktop" in the TikTok app. The script can
start a local server to catch the redirect automatically.

Prerequisites:
  - In TikTok Developer Portal, add a Desktop Redirect URI: http://localhost:8080/callback
  - Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET in .env.
  - Run: python tiktok_oauth_token.py
"""

import hashlib
import secrets
import urllib.parse
import urllib.request
import json
import os
import webbrowser
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# -----------------------------------------------------------------------------
# Config (from env)
# -----------------------------------------------------------------------------
CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "").strip()
CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "").strip()
# Redirect URI must match exactly what you registered (Desktop: http://localhost:PORT/path)
REDIRECT_URI = os.environ.get("TIKTOK_REDIRECT_URI", "http://localhost:8080/callback")
# Scopes: video.publish for posting; user.info.basic for creator info
SCOPE = os.environ.get("TIKTOK_SCOPE", "user.info.basic,video.publish")

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKENS_FILE = os.path.join(SCRIPT_DIR, "tiktok_tokens.json")


def make_code_verifier():
    """PKCE code_verifier (43–128 chars). TikTok allows A-Za-z0-9.-_~"""
    return secrets.token_urlsafe(32)


def make_code_challenge(verifier: str) -> str:
    """S256 code_challenge: TikTok Desktop requires HEX encoding of SHA256, not base64url."""
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return digest.hex()


def build_authorize_url(state: str, code_challenge: str) -> str:
    """Build the TikTok authorize URL with PKCE."""
    params = {
        "client_key": CLIENT_KEY,
        "scope": SCOPE,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)


def exchange_code_for_token(
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict:
    """Exchange authorization code for access_token and refresh_token."""
    data = urllib.parse.urlencode({
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def refresh_access_token(refresh_token: str) -> dict:
    """Get a new access_token using refresh_token."""
    data = urllib.parse.urlencode({
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def save_tokens(tokens: dict) -> None:
    """Write tokens to tiktok_tokens.json."""
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)
    print(f"Tokens saved to: {TOKENS_FILE}")
    print("Add tiktok_tokens.json to .gitignore and do not commit it.")


def run_local_server(redirect_uri: str, result_holder: dict) -> tuple[str, int]:
    """Start a one-request HTTP server to catch the redirect. Returns (host, port)."""
    parsed = urllib.parse.urlparse(redirect_uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8080
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = "/" + path

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith(path):
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                result_holder["code"] = (qs.get("code") or [None])[0]
                result_holder["error"] = (qs.get("error") or [None])[0]
                result_holder["error_description"] = (qs.get("error_description") or [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            if result_holder.get("code"):
                body = b"<h1>Success!</h1><p>You can close this window and return to the script.</p>"
            else:
                err = result_holder.get("error_description") or result_holder.get("error") or "Unknown error"
                body = f"<h1>Error</h1><p>{urllib.parse.unescape(err)}</p>".encode("utf-8")
            self.wfile.write(body)
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, format, *args):  # noqa: ARG002
            pass

    server = HTTPServer((host, port), Handler)
    server.serve_forever()
    return host, port


def main() -> None:
    if not CLIENT_KEY or not CLIENT_SECRET:
        print("Error: Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET in your .env file.")
        print("Example .env:")
        print("  TIKTOK_CLIENT_KEY=your_client_key")
        print("  TIKTOK_CLIENT_SECRET=your_client_secret")
        print("  TIKTOK_REDIRECT_URI=https://localhost/callback   # must match TikTok app")
        return

    print("TikTok OAuth – get user access token\n")
    print(f"Redirect URI (must match TikTok app Desktop URI): {REDIRECT_URI}")
    print(f"Scope: {SCOPE}\n")

    state = secrets.token_urlsafe(16)
    code_verifier = make_code_verifier()
    code_challenge = make_code_challenge(code_verifier)
    url = build_authorize_url(state, code_challenge)

    # Check if redirect URI is localhost/127.0.0.1 with port → use local server
    parsed_redirect = urllib.parse.urlparse(REDIRECT_URI)
    is_local = parsed_redirect.hostname in ("localhost", "127.0.0.1") and parsed_redirect.port
    result_holder = {}

    if is_local:
        port = parsed_redirect.port
        print(f"Starting local server on http://127.0.0.1:{port} to catch redirect...")
        server_thread = threading.Thread(
            target=run_local_server,
            args=(REDIRECT_URI, result_holder),
            daemon=True,
        )
        server_thread.start()
        print("Opening browser for TikTok login and authorization...")
        webbrowser.open(url)
        server_thread.join()
        code = result_holder.get("code")
        if result_holder.get("error") and not code:
            print("Authorization error:", result_holder.get("error_description") or result_holder.get("error"))
            return
    else:
        print("Opening browser for TikTok login and authorization...")
        webbrowser.open(url)
        print("\nAfter you authorize, you will be redirected. Paste the full redirect URL or just the 'code' value.\n")
        raw = input("Paste redirect URL or code: ").strip()
        code = None
        if raw.startswith("http"):
            parsed = urllib.parse.urlparse(raw)
            qs = urllib.parse.parse_qs(parsed.query)
            codes = qs.get("code", [])
            if codes:
                code = codes[0]
            if not code and "error" in qs:
                print("Authorization error:", qs.get("error_description", qs.get("error", "unknown")))
                return
        else:
            code = raw

    if not code:
        print("No authorization code found. Paste the full URL or the code= value.")
        return

    print("\nExchanging code for access token...")
    try:
        result = exchange_code_for_token(code, code_verifier, REDIRECT_URI)
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"Token exchange failed ({e.code}): {body}")
        return
    except Exception as e:
        print(f"Token exchange failed: {e}")
        return

    if "error" in result:
        print("Error:", result.get("error_description", result.get("error", result)))
        return

    access_token = result.get("access_token")
    refresh_token = result.get("refresh_token")
    open_id = result.get("open_id")
    expires_in = result.get("expires_in")

    if not access_token:
        print("Response missing access_token:", result)
        return

    print("Success!")
    print(f"  open_id:      {open_id}")
    print(f"  expires_in:   {expires_in} seconds")
    print(f"  scope:        {result.get('scope', '')}")

    to_save = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "open_id": open_id,
        "expires_in": result.get("expires_in"),
        "refresh_expires_in": result.get("refresh_expires_in"),
        "scope": result.get("scope"),
    }
    save_tokens(to_save)
    print("\nUse access_token in API calls: Authorization: Bearer <access_token>")


if __name__ == "__main__":
    main()
