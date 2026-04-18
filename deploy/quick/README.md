# Go live in ~5 minutes (SQLite)

This is the fastest path to a public HTTPS URL. Later, when you're ready for
multi-instance scale, swap `CPI_SQLITE_PATH` for `CPI_PG_*` (RDS) and migrate
your data with `sqlite3 .dump` -> `psql` — no code changes required.

## Option A — Render.com (recommended, ~5 min)

### 1. Push the repo to GitHub

```powershell
cd c:\Users\cwakh\capital_pay_inventory
git init
git add .
git commit -m "production deploy kit"
git branch -M main
# Create an empty repo on github.com called cpi-inventory then:
git remote add origin https://github.com/<you>/cpi-inventory.git
git push -u origin main
```

### 2. Deploy on Render

1. Sign in to https://render.com with GitHub.
2. **New -> Blueprint**, pick the `cpi-inventory` repo.
3. Render detects `render.yaml` and proposes a web service + 1 GB disk.
4. Click **Apply**. It will fail once because `CPI_BOOTSTRAP_ADMIN_PASSWORD`
   is marked `sync: false` — open the service settings -> **Environment**,
   paste a strong value, and **Save + Deploy**.
5. After ~3 minutes you'll have `https://cpi-inventory.onrender.com`
   (or similar). Log in with `admin` / your bootstrap password, then
   immediately change it from **Configuration -> Users**.

### 3. Point a custom domain (optional)

In Render: **Settings -> Custom Domains -> Add**, follow the DNS instructions.
Render provisions a free Let's Encrypt cert automatically.

### 4. Backups

The SQLite file lives on the disk mounted at `/data`. From the service
**Shell** tab:

```bash
sqlite3 /data/cpi_inventory.sqlite ".backup '/data/backup-$(date +%F).sqlite'"
```

Download backups with `curl -O` through the Render shell or copy them to S3.

---

## Option B — Railway (similar, ~5 min)

1. Install the Railway CLI or use https://railway.app.
2. **New Project -> Deploy from GitHub** -> pick the repo.
3. Add a **Volume** mounted at `/data` (1 GB).
4. Add environment variables:

   | Key | Value |
   | --- | --- |
   | `CPI_ENV` | `production` |
   | `CPI_BEHIND_PROXY` | `1` |
   | `CPI_SESSION_COOKIE_SECURE` | `1` |
   | `CPI_SQLITE_PATH` | `/data/cpi_inventory.sqlite` |
   | `CPI_SECRET_KEY` | *(paste `secrets.token_hex(32)` output)* |
   | `CPI_BOOTSTRAP_ADMIN_USERNAME` | `admin` |
   | `CPI_BOOTSTRAP_ADMIN_PASSWORD` | *(strong value)* |

5. Railway builds the Dockerfile, runs the `CMD` in it, and gives you a
   `*.up.railway.app` URL.

## Option C — Fly.io (great for global edge, ~10 min)

```powershell
flyctl launch --no-deploy                     # detects Dockerfile, asks for app name
flyctl volumes create cpi_data --size 1       # 1 GB persistent disk
# Edit fly.toml -> [mounts] source="cpi_data" destination="/data"
# Edit fly.toml -> [env] CPI_SQLITE_PATH="/data/cpi_inventory.sqlite"
flyctl secrets set CPI_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
flyctl secrets set CPI_BOOTSTRAP_ADMIN_PASSWORD='ChangeMe!123'
flyctl deploy
```

## Option D — Single AWS EC2 + Caddy (stay in AWS, ~20 min)

One t3.small in a public subnet. Caddy does automatic HTTPS.

```bash
# On a fresh Ubuntu 22.04 EC2:
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker ubuntu && newgrp docker

mkdir -p /srv/cpi/data
cd /srv/cpi
cat > docker-compose.yml <<'YAML'
services:
  app:
    image: ghcr.io/<you>/cpi-inventory:latest   # or build locally: docker build -t cpi-inventory .
    restart: unless-stopped
    environment:
      CPI_ENV: production
      CPI_BEHIND_PROXY: "1"
      CPI_SESSION_COOKIE_SECURE: "1"
      CPI_SQLITE_PATH: /data/cpi_inventory.sqlite
      CPI_SECRET_KEY: "REPLACE_WITH_RANDOM_HEX"
      CPI_BOOTSTRAP_ADMIN_USERNAME: admin
      CPI_BOOTSTRAP_ADMIN_PASSWORD: "ChangeMe!123"
    volumes:
      - ./data:/data
  caddy:
    image: caddy:2
    restart: unless-stopped
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    depends_on: [app]
volumes:
  caddy_data: {}
  caddy_config: {}
YAML

cat > Caddyfile <<'CADDY'
inventory.example.com {
  reverse_proxy app:8050
}
CADDY

docker compose up -d
```

Open your DNS provider, point `inventory.example.com` A-record to the EC2
public IP, done. Caddy fetches a TLS cert automatically the first time the
domain resolves.

---

## Mobile app usage

### Log in

```http
POST /api/v1/auth/login
Content-Type: application/json

{"username":"admin","password":"...","label":"my-phone"}
```

Response:

```json
{
  "token": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "token_id": 1,
  "user": {"id": 1, "username": "admin", "full_name": "Admin", "role": "ADMIN"}
}
```

Store `token` in the device keychain. Send it on every subsequent call:

```http
GET /api/v1/items?q=rice
Authorization: Bearer <token>
```

### Available endpoints

| Method | Path | Notes |
| --- | --- | --- |
| GET  | `/api/v1/health` | public liveness |
| POST | `/api/v1/auth/login` | public |
| POST | `/api/v1/auth/logout` | revokes current token |
| GET  | `/api/v1/me` | logged-in user |
| GET  | `/api/v1/items?q=...&active=1` | list / search |
| GET  | `/api/v1/items/{id}` | detail + per-location stock |
| GET  | `/api/v1/stock-by-location` | matrix view |
| GET  | `/api/v1/categories` | reference |
| GET  | `/api/v1/storage-locations` | reference |
| GET  | `/api/v1/suppliers?active=1` | list |
| POST | `/api/v1/suppliers` | create |
| GET  | `/api/v1/customers?active=1` | list |
| POST | `/api/v1/customers` | create |
| GET  | `/api/v1/alerts?limit=100` | low-stock / expiry feed |
| GET  | `/api/v1/sales-orders?limit=100` | list |
| POST | `/api/v1/sales-orders` | `{customer_id, lines:[{item_id,qty,unit_price}]}` |
| POST | `/api/v1/movements/issue` | `{item_id, quantity, storage_location_id?}` |
| POST | `/api/v1/movements/receive` | `{item_id, quantity, unit_cost, storage_location_id?}` |

All errors return JSON `{"error": "..."}` with an appropriate HTTP status
(400 validation, 401 auth, 404 missing, 500 unexpected).

### CORS (web front-end only)

Mobile apps don't need CORS. If you want to call the API from a browser app,
set `CPI_API_CORS_ORIGINS=https://yourapp.com,https://admin.yourapp.com` in
the service environment.

---

## Migrating SQLite -> RDS later

When you're ready to move to Postgres:

```bash
# 1. Dump SQLite as SQL
sqlite3 /data/cpi_inventory.sqlite .dump > dump.sql

# 2. Clean SQLite-isms (AUTOINCREMENT, PRAGMA) in dump.sql (sed/editor).
# 3. Create the schema on RDS using the app itself:
CPI_PG_HOST=... CPI_PG_USER=... CPI_PG_PASSWORD=... CPI_PG_DB=... \
    python -c "from database.engine import init_database; init_database()"

# 4. Load the data tables-only via `pgloader` (recommended) or a small script:
pgloader sqlite:///data/cpi_inventory.sqlite \
    postgresql://USER:PASS@HOST:5432/DBNAME

# 5. Switch env vars (comment CPI_SQLITE_PATH, uncomment CPI_PG_*) and restart.
```

No code changes — the engine auto-detects which backend to use.
