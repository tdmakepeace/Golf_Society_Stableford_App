# Screenshots for the main README

The root [README.md](../../README.md) references PNGs in this folder. Re-capture after UI changes so the README stays accurate.

## Regenerate (Playwright)

With the Flask app already running on `http://127.0.0.1:5000`:

```bash
pip install -r requirements-dev.txt
playwright install chromium
python scripts/capture_readme_screenshots.py
```

Optional: `BASE_URL`, `COMPETITION_ID` (defaults `1`).

**Demo logins** (see README Screenshots section for the full table):

| Role | Email | Password |
|------|-------|----------|
| Super admin | `superadmin@example.com` | `GolfSuper1!` |
| Society admin | `test@test.com` | `Test123!` |
| Player | `toby@test.com` | Competition password `Test123!` (set on the demo competition for capture) |

| Filename | Suggested capture |
|----------|-------------------|
| `01-home.png` | Landing page `/` |
| `02-admin-login.png` | Society admin login `/admin/login` |
| `03-admin-dashboard.png` | Society admin dashboard `/admin/` (signed in as society admin) |
| `04-results.png` | Competition results `/admin/competitions/<id>/results` |
| `05-player-login.png` | Player login `/login` |

Optional extras for a future README row: super admin dashboard, course editor, competition detail (lock / players), player scorecard.
