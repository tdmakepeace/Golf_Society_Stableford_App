"""Run the Golf Society Stableford app: `python run.py` or `flask --app run run`."""

from app import create_app

# --- local run settings (edit here) ---
# True = auto-reload on file changes. If False, restart this process after editing Python (e.g. stableford).
DEBUG = True  # True for development, False for production
IP = "0.0.0.0"  # use "0.0.0.0" to listen on all interfaces (reachable on your LAN host IP), or 127.0.0.1 for local access only
PORT = 5000 # the port to listen on

app = create_app()

if __name__ == "__main__":
    app.run(debug=DEBUG, host=IP, port=PORT)
