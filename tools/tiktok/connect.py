#!/usr/bin/env python3
"""Connect the academy's TikTok account to the poster, or refresh its token.

    py -3 tiktok/connect.py            # opens TikTok in the browser; you approve; the token is saved
    py -3 tiktok/connect.py refresh    # renews the access token (it lasts 24 h; the refresh token 365 days)
    py -3 tiktok/connect.py whoami     # shows which TikTok account the saved token belongs to

Reads TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET and TIKTOK_REDIRECT_URI from .env at the
project root and writes tiktok/token.json. Both files are private: never share or commit them.
"""
import hashlib
import http.server
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN = ROOT / "tiktok" / "token.json"
SCOPES = "user.info.basic,video.upload"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_URL = "https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name"


def env():
    """Settings from .env (on the laptop) overlaid by real environment variables (in the cloud)."""
    vals = {}
    if (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    vals.update({k: v.strip() for k, v in os.environ.items() if k.startswith(("TIKTOK_", "GITHUB_", "SITE_")) and v.strip()})
    missing = [k for k in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET") if not vals.get(k)]
    if missing:
        sys.exit(f"STOP .env is missing {', '.join(missing)}")
    return vals


def post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        data = json.loads(e.read() or b"{}")
    if "access_token" not in data:
        sys.exit(f"STOP TikTok refused the token request: {data.get('error')} {data.get('error_description', '')}")
    return data


def save(data):
    data["obtained_at"] = int(time.time())
    TOKEN.write_text(json.dumps(data, indent=1), encoding="utf-8")


def whoami():
    tok = json.loads(TOKEN.read_text(encoding="utf-8"))
    req = urllib.request.Request(USER_URL, headers={"Authorization": f"Bearer {tok['access_token']}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        user = json.loads(r.read())["data"]["user"]
    left = tok["obtained_at"] + tok["expires_in"] - time.time()
    print(f"connected: {user.get('display_name')}  scopes: {tok.get('scope')}  token valid {left / 3600:.1f} h more")


def connect():
    cfg = env()
    cfg.setdefault("TIKTOK_REDIRECT_URI", "http://localhost:3455/callback/")
    redirect = urllib.parse.urlparse(cfg["TIKTOK_REDIRECT_URI"])
    verifier = secrets.token_urlsafe(64)[:96]
    state = secrets.token_urlsafe(16)
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_key": cfg["TIKTOK_CLIENT_KEY"], "scope": SCOPES, "redirect_uri": cfg["TIKTOK_REDIRECT_URI"],
        "state": state, "response_type": "code",
        "code_challenge": hashlib.sha256(verifier.encode()).hexdigest(),  # TikTok desktop wants hex, not base64url
        "code_challenge_method": "S256"})
    result = {}

    class Callback(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path.rstrip("/") != redirect.path.rstrip("/"):
                self.send_response(404)
                self.end_headers()
                return
            result.update({k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()})
            ok = "code" in result and result.get("state") == state
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Connected. You can close this tab." if ok else "Something went wrong. Check the terminal."
            self.wfile.write(f"<body style='font:20px sans-serif;padding:40px'>{msg}</body>".encode())

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("localhost", redirect.port), Callback)
    print("Opening TikTok in your browser. Sign in with the ACADEMY account and approve.")
    print(f"If nothing opens, paste this into your browser:\n{url}\n")
    webbrowser.open(url)
    server.timeout = 300
    while not result:
        server.handle_request()
    server.server_close()

    if result.get("state") != state:
        sys.exit("STOP the reply did not match this request (state mismatch). Run connect again.")
    if "code" not in result:
        sys.exit(f"STOP TikTok returned {result.get('error')}: {result.get('error_description', '')}")
    save(post_form(TOKEN_URL, {
        "client_key": cfg["TIKTOK_CLIENT_KEY"], "client_secret": cfg["TIKTOK_CLIENT_SECRET"],
        "code": result["code"], "grant_type": "authorization_code",
        "redirect_uri": cfg["TIKTOK_REDIRECT_URI"], "code_verifier": verifier}))
    whoami()


def refresh():
    cfg = env()
    tok = json.loads(TOKEN.read_text(encoding="utf-8"))
    save(post_form(TOKEN_URL, {
        "client_key": cfg["TIKTOK_CLIENT_KEY"], "client_secret": cfg["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]}))
    whoami()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "connect"
    {"connect": connect, "refresh": refresh, "whoami": whoami}.get(cmd, lambda: sys.exit(__doc__))()
