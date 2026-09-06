"""One-time local OAuth 2.0 PKCE helper for X Radar.

Run locally with X_CLIENT_ID and X_CLIENT_SECRET from the X App.
The callback must be registered as http://127.0.0.1:8765/callback.
"""
import base64
import hashlib
import http.server
import os
import secrets
import threading
import urllib.parse
import webbrowser

import requests

REDIRECT_URI = "http://127.0.0.1:8765/callback"
AUTH_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
SCOPES = "tweet.read users.read offline.access"
result = {}


def handler_factory(state):
    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if params.get("state", [""])[0] != state:
                self.send_error(400, "Invalid OAuth state")
                return
            result.update({key: values[0] for key, values in params.items()})
            body = b"Authorization received. You can close this browser tab."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    return CallbackHandler


def main():
    client_id = os.getenv("X_CLIENT_ID")
    client_secret = os.getenv("X_CLIENT_SECRET")
    if not client_id:
        raise SystemExit("Set X_CLIENT_ID first (from the X App settings).")
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(32)
    params = {"response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT_URI,
              "scope": SCOPES, "state": state, "code_challenge": challenge,
              "code_challenge_method": "S256"}
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)
    server = http.server.HTTPServer(("127.0.0.1", 8765), handler_factory(state))
    print("Opening X authorization page...")
    webbrowser.open(url)
    server.handle_request()
    if "error" in result:
        raise SystemExit(f"X authorization failed: {result['error']}")
    data = {"code": result.get("code"), "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI, "code_verifier": verifier, "client_id": client_id}
    auth = (client_id, client_secret) if client_secret else None
    response = requests.post(TOKEN_URL, data=data, auth=auth, timeout=30)
    response.raise_for_status()
    tokens = response.json()
    print("\nCopy this access token into GitHub Actions Secret X_USER_ACCESS_TOKEN:\n")
    print(tokens["access_token"])
    print("\nRefresh token received:", "yes" if tokens.get("refresh_token") else "no")


if __name__ == "__main__":
    main()
