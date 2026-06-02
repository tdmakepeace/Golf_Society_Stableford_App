# Golf Society Stableford App

A small **Flask** app for running Stableford golf competitions with a three-tier model:

- **Super admins** create societies.
- **Society admins** manage courses, competitions, and society players.
- **Players** enter scores for competitions they are entered in.

Data is stored in **SQLite** at `instance/golfsociety.sqlite` and survives restarts.

---

## Screenshots

PNG files live under [`docs/screenshots/`](docs/screenshots/) (see [`docs/screenshots/README.md`](docs/screenshots/README.md) for filenames). Regenerate them with the app running: `pip install -r requirements-dev.txt`, `playwright install chromium`, then `python scripts/capture_readme_screenshots.py` (optional env: `BASE_URL`, `COMPETITION_ID`).

**Sample accounts used when capturing screenshots** (your data may differ):

| Role | URL | Email | Password |
|------|-----|-------|----------|
| Super admin | `/super-admin/login` | `superadmin@example.com` | `GolfSuper1!` |
| Society admin | `/admin/login` | `test@test.com` | `Test123!` |
| Player | `/login` | `toby@test.com` | Society shared player password or personal password |

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

Override with `BOOTSTRAP_SUPER_ADMIN_EMAIL` and `BOOTSTRAP_SUPER_ADMIN_PASSWORD` (must pass validation).

**Flow:** Super admin signs in and creates society (name + first society admin + shared player password) -> society admin signs in and manages users, courses, and competitions.

**CLI:** `flask --app run create-society-admin email@example.com 'Pass1!word' SOCIETY_ID` adds another society admin to an existing society.

---

## How the logic works

### Roles

- **Super admin** (`/super-admin/login`): create societies and first society admin, lock/unlock societies, manage super admins, manage own password.
- **Society admin** (`/admin/login`): manage society players (including archive/restore), shared player password, competitions, courses, and results/PDF.
- **Players** (`/login`): sign in with **email + personal password** or **email + society shared player password**, then can submit scores for competitions they are entered in.

### Society players and competition entries

- Players are created at **society** level.
- In competition setup, add-player dropdown shows only **active** society players **not already in that competition**.
- Players can be marked deleted (archived) from society players; archived players are hidden from active lists and excluded from new competition add/import. They can be restored.

### Competition management (society admin)

- **Competition handicap is event-specific** and stored per competition entry.
- **Handicap copy-forward:** when adding a player and leaving handicap blank, the app copies their handicap from their most recent previous competition in that society.
- **Lock competition:** while locked, players cannot change scores; roster changes/import/handicap edits/removals are blocked.
- **Remove player from competition:** removes that player only from the event and deletes their scores for that event.

### Stableford points (per hole)

Net strokes for a hole = **gross - handicap strokes on that hole**.

**Handicap strokes on a hole** (`app/stableford.py`):

1. `base = playing_handicap // 18` -> every hole receives `base`.
2. `remainder = playing_handicap % 18`.
3. If `remainder > 0`, each hole gets one extra on holes where **stroke index >= 19 - remainder**.

In this app, **SI 18 is hardest** and **SI 1 easiest**.

Points vs par:

| vs par | Points |
|--------|--------|
| 3+ under | 5 |
| 2 under | 4 |
| 1 under | 3 |
| Par | 2 |
| 1 over | 1 |
| 2+ over | 0 |

### Courses and stroke index (SI)

- Courses are shared across societies.
- Each course has exactly 18 holes.
- Hole constraints:
  - Par: `3..6`
  - Stroke index: `1..18`, unique per course
- Course deletion allowed only when unused by competitions.

---

## Run locally

```bash
pip install -r requirements.txt
python run.py
```

Open `http://127.0.0.1:5000/`.

`run.py` controls local debug settings. For production, set a strong `SECRET_KEY`.

---

## Run with Docker

The repo includes `Dockerfile` and `docker-compose.yml`.

SQLite is stored at `/app/instance` in container and persisted via:

`./instance` (host) -> `/app/instance` (container)

### Start

```bash
mkdir instance
docker compose up --build -d
```

Open `http://localhost:5000/`.

### Rebuild with no cache

Use this when you need a completely fresh image build:

```bash
docker compose build --no-cache
docker compose up -d
```

Or in one command:

```bash
docker compose up --build --force-recreate -d
```

### Stop

```bash
docker compose down
```

Database remains at `instance/golfsociety.sqlite`.

### Environment variables with `docker-compose.override.yaml`

`docker-compose.yml` already maps:

- `SECRET_KEY`
- `BOOTSTRAP_SUPER_ADMIN_EMAIL`
- `BOOTSTRAP_SUPER_ADMIN_PASSWORD`

Preferred approach is keeping local env values in `docker-compose.override.yaml` (auto-loaded by Compose) rather than editing base compose file.

Example `docker-compose.override.yaml`:

```yaml
services:
  golfsociety:
    environment:
      SECRET_KEY: "replace-with-strong-secret"
      BOOTSTRAP_SUPER_ADMIN_EMAIL: "superadmin@example.com"
      BOOTSTRAP_SUPER_ADMIN_PASSWORD: "GolfSuper1!"
```

Then run:

```bash
docker compose up --build -d
```

PowerShell alternative (session-only env vars):

```powershell
$env:SECRET_KEY="replace-with-strong-secret"
$env:BOOTSTRAP_SUPER_ADMIN_EMAIL="superadmin@example.com"
$env:BOOTSTRAP_SUPER_ADMIN_PASSWORD="GolfSuper1!"
docker compose up --build -d
```

### Alternative without Compose

```bash
mkdir instance
docker build -t golfsociety .
docker run -d --name golfsociety-app -p 5000:5000 -v ${PWD}/instance:/app/instance golfsociety
```

---

## Project layout (high level)

| Path | Purpose |
|------|---------|
| `app/__init__.py` | App factory, session/login setup, SQLite migration hook, CLI |
| `app/models.py` | Super admins, societies, admins, users, courses, holes, competitions, scores |
| `app/stableford.py` | Handicap/stableford math |
| `app/scoring_helpers.py` | Leaderboards and scorecard helpers |
| `app/super_admin_routes.py` / `admin_routes.py` / `user_routes.py` / `main_routes.py` | HTTP routes |
| `app/db_migrate.py` | SQLite upgrades from earlier schema versions |
| `templates/` | Jinja templates |
| `static/style.css` | Theme/layout |
| `docs/images/` | Diagrams |
| `docs/screenshots/` | Screenshot assets |
| `instance/golfsociety.sqlite` | SQLite database |

---

## CSV import

Expected columns (header row): **`email`** and **`handicap`** (aliases like `e_mail`, `playing_handicap`, `hcp` are accepted).

Import only adds/updates **active society players**. Archived/deleted players are skipped until restored.
