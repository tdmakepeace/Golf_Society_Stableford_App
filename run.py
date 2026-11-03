"""Run the Golf Society Stableford app: `python run.py` or `flask --app run run`."""

from __future__ import annotations

import os

from app import create_app
from app.dev_https import ensure_dev_certificate, https_access_urls

# --- local run settings (edit here) ---
# True = auto-reload on file changes. If False, restart this process after editing Python (e.g. stableford).
DEBUG = True  # True for development, False for production
IP = "0.0.0.0"  # use "0.0.0.0" to listen on all interfaces (reachable on your LAN host IP), or 127.0.0.1 for local access only
PORT = 5000  # the port to listen on
# Self-signed HTTPS in certs/ (local and Docker). Set USE_HTTPS=0 to force plain HTTP.
USE_HTTPS = os.environ.get("USE_HTTPS", "1") != "0"

# Docker image sets FLASK_ENV=production; keep debug off there even if DEBUG=True above.
if os.environ.get("FLASK_ENV") == "production":
    DEBUG = False

app = create_app()

if __name__ == "__main__":
    ssl_context = None
    if USE_HTTPS:
        cert_path, key_path = ensure_dev_certificate()
        ssl_context = (str(cert_path), str(key_path))
        app.config["SESSION_COOKIE_SECURE"] = True
        print("HTTPS enabled (self-signed). Open one of:")
        for url in https_access_urls(PORT):
            print(f"  {url}")
        print(
            "First phone visit: accept the browser certificate warning once "
            "(Advanced, then continue). Set USE_HTTPS=0 for plain HTTP."
        )
    app.run(debug=DEBUG, host=IP, port=PORT, ssl_context=ssl_context)
