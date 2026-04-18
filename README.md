# Stock inventory (Plotly Dash + Dash Mantine)

Web application for **inventory, movements, purchase orders, approvals, and reporting** backed by PostgreSQL.

## How to run in PyCharm

### 1. Get the project

- Unzip `capital_pay_inventory.zip` anywhere (e.g. `C:\Projects\capital_pay_inventory`).

### 2. Open in PyCharm

1. **File → Open** → select the `capital_pay_inventory` folder (the one that contains `app.py`).
2. PyCharm may ask to trust the project — choose **Trust Project**.

### 3. Python interpreter

1. **File → Settings** (Windows) → **Project: capital_pay_inventory → Python Interpreter**.
2. Click the gear → **Add Interpreter → Add Local Interpreter**.
3. Choose **Virtualenv** (recommended), base Python **3.10+**, then **OK**.

### 4. Install dependencies

Open the **Terminal** at the bottom of PyCharm (it should already be in the project folder) and run:

```bash
pip install -r requirements.txt
```

If PyCharm didn’t activate the venv, use the full path to its `pip`, or run:

```bash
python -m pip install -r requirements.txt
```

### 5. Run the app

**Default:** `python app.py` starts the **Flask** development server (best compatibility with Dash multi‑page callbacks).

**Optional FastAPI:** set environment variable `CPI_USE_UVICORN=1` before `python app.py`, or run Uvicorn directly. Health check when using ASGI: `http://127.0.0.1:8050/api/health`.

**Option A — Run `app.py`**

1. Open `app.py` in the editor.
2. Right‑click in the editor → **Run 'app'** (or click the green play gutter next to `if __name__ == "__main__"`).

**Option B — Uvicorn (FastAPI + WSGI mount)**

```bash
uvicorn asgi:application --host 127.0.0.1 --port 8050 --reload
```

Or: `set CPI_USE_UVICORN=1` (Windows) / `export CPI_USE_UVICORN=1` (macOS/Linux), then `python app.py`.

**Option C — PyCharm run configuration**

1. **Run → Edit Configurations…**
2. **+ → Python**
3. **Script path:** point to `app.py` in this project.
4. **Working directory:** the project root (same folder as `app.py`).
5. **OK**, then **Run**.

### 6. Open in browser

The console will show the server on `http://127.0.0.1:8050`. Open that URL, log in, then use the sidebar.

### Production first run

With `CPI_ENV=production` (or `CPI_SEED_MODE=minimal`), the database gets **roles, alert rules, and system defaults only** — no sample SKUs or accounts. Create the first administrator with:

`python -m database.create_bootstrap_admin --username <login> --password '<strong password>'`

(or set `CPI_BOOTSTRAP_ADMIN_PASSWORD` once for the first process start; see `.env.example`). Remove bootstrap secrets from the environment after login.

To wipe all row data before go-live: `python -m database.clear_all_data --yes`

### Local development demo dataset

Set `CPI_SEED_MODE=demo` (and an empty `users` table) to load the bundled **demo** inventory and a default `admin` user with password `admin` — **never use this in production**.

### What each role sees (sidebar)

| Role | Areas |
|------|--------|
| **VIEWER** | Dashboard, Reports, Alerts (read-only; cannot acknowledge alerts) |
| **STOCK_CLERK** | Dashboard, Operations (inventory, movements, POs, suppliers, audits), Reports, Alerts — **inventory edits are queued** until a manager approves them with a PIN |
| **MANAGER** | Same as clerk **plus** **Approvals** (review/approve clerk inventory changes with PIN) and **Configuration** (set/change/remove that PIN); still no **Users** (admin-only) |
| **ADMIN** | Everything, including **Users**, **Approvals**, and approval PIN in **Configuration** |

Direct URLs to forbidden pages redirect to the dashboard.

### Database

- PostgreSQL is required. Set `CPI_DATABASE_URL` before starting the app.

### Environment (optional)

See **`.env.example`** for all variables. Common ones:

- `CPI_SECRET_KEY` — Flask session secret (defaults to a **dev-only** value; **required** when `CPI_ENV=production`).
- `CPI_ENV` — set to `production` for hardened cookies and secret validation.
- `CPI_DATABASE_URL` — PostgreSQL connection string for the app database.
- `CPI_HOST` / `CPI_PORT` — bind address for `python app.py` or Uvicorn.
- `CPI_DEBUG` — `true`/`false` for local `python app.py` (ignored in production).
- `CPI_BEHIND_PROXY` — `1` when running behind nginx/Traefik (enables `ProxyFix`).
- `CPI_SESSION_COOKIE_SECURE` — `1` when the site is served only over HTTPS.

### Production deployment

**1. WSGI (recommended for Linux)**

Install dependencies, set secrets, then:

```bash
export CPI_ENV=production
export CPI_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export CPI_DATABASE_URL="postgresql+psycopg://user:pass@host:5432/dbname?sslmode=require"
gunicorn --bind 0.0.0.0:8050 --workers 2 --threads 4 --timeout 120 wsgi:application
```

Entry point: **`wsgi:application`** (same Flask `server` Dash uses).

**2. Windows / local production-style run**

Gunicorn is not installed on Windows via `requirements.txt`. Use **Waitress**:

```bash
waitress-serve --listen=0.0.0.0:8050 wsgi:application
```

**3. Optional: container image for the app only**

`Dockerfile` can build the web app image; use your own managed PostgreSQL (e.g. AWS RDS) and set `CPI_DATABASE_URL` or `CPI_PG_*` in the runtime environment. Put TLS termination and `CPI_BEHIND_PROXY=1` / `CPI_SESSION_COOKIE_SECURE=1` in your reverse proxy as needed.

**4. ASGI (optional)**

```bash
uvicorn asgi:application --host 0.0.0.0 --port 8050
```

FastAPI exposes **`GET /api/health`** and **`GET /api/db/health`** (DB connectivity via pooled sessions) above the Dash app; Flask REST tokens remain under **`/api/v1/`**.

### Single command (outside PyCharm)

From the project root:

```bash
python app.py
```

FastAPI mode (optional):

```bash
set CPI_USE_UVICORN=1
python app.py
```

### Browser error: `useId is not a function`

`app.py` already calls `dash._dash_renderer._set_react_version("18.2.0")` so Mantine works with Dash 2.x. If you removed that line, restore it **before** `dash.Dash(...)`, or add a `.env` file in the project root with:

```bash
REACT_VERSION=18.2.0
```
