#!/usr/bin/env python3
"""
Obtain a TikTok user access token for the Content Posting API (desktop OAuth with PKCE).

Prerequisites:
  - TikTok app in Production with Login Kit and Content Posting API.
  - In Login Kit → Desktop, add redirect URI: http://localhost:8080/callback/
  - .env (or env) with TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET.

Run: python tiktok_get_token.py
A browser will open; after you log in and approve, the script saves the token.
"""

import hashlib
import json
import os
import random
import secrets
import string
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# -----------------------------------------------------------------------------
# Config – must match TikTok app (Production)
# -----------------------------------------------------------------------------
REDIRECT_URI = "http://localhost:8080/callback/"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
SCOPE = "video.publish"  # for Content Posting API direct post
PORT = 8080
TOKENS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiktok_tokens.json")


def generate_code_verifier(length: int = 64) -> str:
    """PKCE code verifier: 43–128 chars, unreserved [A-Za-z0-9-._~]."""
    chars = string.ascii_letters + string.digits + "-._~"
    return "".join(secrets.choice(chars) for _ in range(length))


def code_challenge_from_verifier(verifier: str) -> str:
    """S256 code challenge = hex(SHA256(verifier))."""
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return digest.hex()


def exchange_code_for_token(
    client_key: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict:
    """Exchange authorization code for access_token (desktop: include code_verifier)."""
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "").strip()
    if not client_key or not client_secret:
        print("Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET in .env or environment.")
        return

    state = "".join(random.choices(string.ascii_letters + string.digits, k=24))
    code_verifier = generate_code_verifier()
    code_challenge = code_challenge_from_verifier(code_verifier)

    auth_params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": SCOPE,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    qs = "&".join(f"{k}={v}" for k, v in auth_params.items())
    auth_full_url = f"{AUTH_URL}?{qs}"

    result = {"code": None, "state_ok": False, "token_data": None}
    token_data_holder = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path.rstrip("/") != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            params = parse_qs(parsed.query)
            code_list = params.get("code")
            state_list = params.get("state")
            error_list = params.get("error")
            if error_list:
                err_desc = params.get("error_description", ["Unknown"])[0]
                body = f"<html><body><p>Authorization failed: {err_desc}</p></body></html>"
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(body.encode())
                result["code"] = None
                return
            if code_list and state_list and state_list[0] == state:
                result["code"] = code_list[0]
                result["state_ok"] = True
                body = "<html><body><p>Authorization successful. You can close this tab.</p></body></html>"
            else:
                body = "<html><body><p>Missing code or state mismatch. Try again.</p></body></html>"
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("", PORT), Handler)
    print(f"Redirect URI in your app must be: {REDIRECT_URI}")
    print("Opening browser for TikTok login...")
    webbrowser.open(auth_full_url)
    server.handle_request()
    server.server_close()

    if not result["state_ok"] or not result["code"]:
        print("No authorization code received. Check redirect URI and try again.")
        return

    print("Exchanging code for token...")
    token_data = exchange_code_for_token(
        client_key, client_secret, result["code"], REDIRECT_URI, code_verifier
    )

    # Save tokens (response may use access_token, refresh_token, open_id, etc.)
    to_save = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "open_id": token_data.get("open_id"),
        "expires_in": token_data.get("expires_in"),
        "scope": token_data.get("scope"),
    }
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2)
    print(f"Tokens saved to {TOKENS_FILE}")
    print("Use access_token in the Authorization header: Bearer <access_token>")


if __name__ == "__main__":
    main()
