# Golf Society Stableford App

A small **Flask** app for running a **Stableford** golf competition: **super admins** create societies and the first **society admin**; society admins add **shared courses** (18 holes: par + stroke index) and their own **competitions**; **players** enter scores using the **competition password**.

Data is stored in **SQLite** at `instance/golfsociety.sqlite` and survives restarts.

---

## Screenshots

PNG files live under [`docs/screenshots/`](docs/screenshots/) (see [`docs/screenshots/README.md`](docs/screenshots/README.md) for filenames). Regenerate them with the app running: `pip install -r requirements-dev.txt`, `playwright install chromium`, then `python scripts/capture_readme_screenshots.py` (optional env: `BASE_URL`, `COMPETITION_ID`).

**Sample accounts used when capturing the screenshots below** (your database may differ):

| Role | URL | Email | Password |
|------|-----|-------|----------|
| Super admin | `/super-admin/login` | `superadmin@example.com` | `GolfSuper1!` |
| Society admin | `/admin/login` | `test@test.com` | `Edcvfr1!` |
| Player | `/login` | `toby@test.com` | **`Edcvfr1!`** as the **competition password** (same string used for society admin in the capture DB; players always use the organiser’s event password, not a personal password) |

| Home | Society admin login |
|------|---------------------|
| ![Home](docs/screenshots/01-home.png) | ![Society admin login](docs/screenshots/02-admin-login.png) |

| Society admin dashboard | Results |
|-------------------------|---------|
| ![Society admin dashboard](docs/screenshots/03-admin-dashboard.png) | ![Results](docs/screenshots/04-results.png) |

| Player login |
|--------------|
| ![Player login](docs/screenshots/05-player-login.png) |

### Stroke index and handicap (diagram)

How stroke index interacts with playing handicap in code (matches the course editor help text):

![Stroke index: SI 18 hardest; remainder shots on highest SI first](docs/images/stroke-index-convention.svg)

### Full-page background (optional)

The UI uses a full-page background defined in [`static/style.css`](static/style.css). To show the golf-course photo, add:

`static/images/golf-course-bg.jpg`

If that file is missing, the gradient overlay still applies; only the photograph is absent.

---

## First login after deleting SQLite

If there are **no super admins**, the app creates one on startup:

| | |
|--|--|
| **Email** | `superadmin@example.com` |
| **Password** | `GolfSuper1!` |

Override with `BOOTSTRAP_SUPER_ADMIN_EMAIL` and `BOOTSTRAP_SUPER_ADMIN_PASSWORD` (must pass the same validation rules).

**Flow:** sign in at **Super admin** → **Create society** (name + first society admin email/password) → that person signs in at **Society admin** to add courses and competitions.

**CLI:** `flask --app run create-society-admin email@example.com 'Pass1!word' SOCIETY_ID` adds another society admin to an existing society (use the society id from the database or super admin UI list).

---

## How the logic works

### Roles

- **Super admin** (`/super-admin/login`): create societies and the **first** society admin for each; **Admins & passwords** per society; **Lock / unlock** a society (society admins cannot sign in or use `/admin` while locked); **My password** and **Super admins** to change your own password, add additional super admins, or remove others (never the last account, never yourself while signed in).
- **Society admin** (`/admin/login`): sees **all courses** in that society (any society admin can edit); creates **competitions** and only sees **their own** competitions and results; can add more society admins (**Society admin** in the header nav includes a **Home** link back to the dashboard). If the society is **locked** by a super admin, sign-in and the admin area are blocked until it is unlocked.
- **Players** (login at `/login`): enter scores only for competitions they belong to, using the **competition password** (not a personal password).

### Competition management (society admin)

- **Lock competition:** while locked, players cannot change scores (scorecard is read-only); roster changes, CSV import, competition password changes, and per-player **Remove** are disabled until unlock. Deleting the whole competition and viewing **Results** still work.
- **Remove player:** removes that player from the event and deletes **all scores** for that player in that competition only (the global user account remains for other events).

### Stableford points (per hole)

Net strokes for a hole = **gross − handicap strokes on that hole**.

**Handicap strokes on a hole** (`app/stableford.py`):

1. `base = playing_handicap // 18` — full sets of 18 shots; **every** hole receives `base` strokes.
2. `remainder = playing_handicap % 18`. If `remainder` is 0 (e.g. playing handicap **18**, **36**, or **54**), **no** hole gets an extra stroke from the remainder: every hole shows the same total handicap shots, and stroke index does not redistribute anything (there is nothing left to split).
3. If `remainder > 0`, each hole gets **one extra** stroke on holes where **stroke index ≥ 19 − remainder**. Because **SI 18 is the hardest hole** in this app, spare shots go to the **highest** stroke indexes first (then 17, 16, … until `remainder` holes have been given an extra shot).

Example: playing handicap **5** → `base = 0`, `remainder = 5` → extra stroke on holes whose SI is in **14, 15, 16, 17, 18** (the five hardest by this numbering).

Points vs **par** for that net score:

| vs par | Points |
|--------|--------|
| 3+ under | 5 |
| 2 under (eagle) | 4 |
| 1 under (birdie) | 3 |
| Par | 2 |
| 1 over (bogey) | 1 |
| 2+ over | 0 |

Totals are summed for the round.

### Competition password

Each competition has **one shared password** (stored hashed). Players sign in with **email + that password**. The session records which competition(s) matched so they only see those events. CSV import and single-player add only need **email** and **handicap**; new player accounts get an internal random credential players never use.

### Courses and stroke index (SI)

- **Scope:** Courses belong to the **society**; every society admin can create or edit them. Competitions pick a course from that society.
- **Holes:** Exactly **18** holes per course. For each hole you set:
  - **Par** — integer from **3** to **6**.
  - **Stroke index** — integer from **1** to **18**, **unique** across the course (the editor enforces uniqueness 1–18).
- **Meaning of SI in this app:** **18 = hardest hole** on the card (first in line for remainder handicap shots); **1 = easiest**. Enter values so they match **your** society scorecard; the Stableford math uses the convention above.
- **Delete:** A course can be **deleted** only if no competition references it.

### “Your par” on results

Under each player, the **Par** row is **course par + handicap strokes on that hole** (the gross score that would be net par for that player), so different handicaps show different targets.

---

## Run locally

```bash
pip install -r requirements.txt
python run.py
```

Open `http://127.0.0.1:5000/` — choose **Player login** or **Admin login**.

`run.py` sets **Flask `debug`** (see file comments). With debug off, restart the process after changing Python files. For production, set a strong `SECRET_KEY` in the environment.

---

## Project layout (high level)

| Path | Purpose |
|------|---------|
| `app/__init__.py` | App factory, SQLite migration hook, **bootstrap admin**, CLI |
| `app/models.py` | Admins, users, courses, holes, competitions, scores |
| `app/stableford.py` | Handicap strokes and Stableford points |
| `app/scoring_helpers.py` | Leaderboards and player scorecards |
| `app/super_admin_routes.py` / `admin_routes.py` / `user_routes.py` / `main_routes.py` | HTTP routes |
| `app/db_migrate.py` | SQLite upgrades from older single-tier installs |
| `templates/` | Jinja pages |
| `static/style.css` | Layout, theme, optional `static/images/golf-course-bg.jpg` |
| `docs/images/` | Diagrams for documentation (e.g. stroke index SVG) |
| `docs/screenshots/` | Optional UI screenshots referenced above |
| `instance/golfsociety.sqlite` | Database (created on first run) |

---

## CSV import

Expected columns (header row): **`email`** and **`handicap`** (aliases such as `e_mail`, `playing_handicap`, `hcp` are accepted). No passwords in the file — players use the **competition password** set on the competition page.
