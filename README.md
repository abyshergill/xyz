# YourTrolley

A Django-based web application for managing multiple independent food
stalls/stores on one platform: customer ordering, QR-code menu access,
order management & merging, billing/tax configuration, and a sales/CRM
analytics dashboard for store owners.

## Tech stack

- **Backend:** Django 6.x
- **Database:** SQLite (active, default) / PostgreSQL (configured, commented out — see `config/settings.py`)
- **Images:** Pillow (auto-compresses/resizes uploads, validates real image content)
- **QR codes:** `qrcode[pil]`, generated automatically when a store is created
- **Frontend:** Tailwind CSS (Play CDN) — mobile-first, responsive
- **Charts:** Chart.js, fed by JSON aggregated server-side via the Django ORM
- **Reverse proxy / TLS:** Caddy (sample `Caddyfile` included)

## Project layout

```
config/            # settings, root urls, wsgi/asgi
accounts/          # custom User model (ADMIN/OWNER/CUSTOMER roles), RBAC middleware, auth views
stores/            # Store, OperatingHours, Category, FoodItem; QR + image utils
orders/            # Order, OrderItem, TaxConfiguration; merge logic in orders/services.py
analytics/         # CRM/sales dashboard (daily/weekly/monthly, item & category breakdowns)
platform_admin/    # platform-wide admin overview dashboard
templates/         # all HTML templates, organized per app
static/            # CSS
Caddyfile           # sample production reverse-proxy config
requirements.txt
.env.example         # copy to .env and fill in for real deployments
SECURITY.md          # OWASP Top 10 implementation + testing notes
```

## Getting started (local development)

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser    # for /django-admin/ and to set role=ADMIN
python manage.py runserver
```

Visit `http://127.0.0.1:8000/`. SQLite (`db.sqlite3`) is used automatically —
no extra configuration needed for local development.

Superusers created via `createsuperuser` are now automatically given the
Platform Admin role, so they can access both `/django-admin/` and the
platform's own `/platform-admin/dashboard/` right away — no extra step
needed.

### Quick-start demo accounts

Don't want to register manually? Run:

```bash
python manage.py seed_demo_data
```

This creates three ready-to-use accounts (safe to re-run; it won't touch
accounts that already exist):

| Role | Username | Password | What happens on login |
|---|---|---|---|
| Platform Admin | `admin_demo` | `Admin@12345` | Goes straight to `/platform-admin/dashboard/` |
| Store Owner | `owner_demo` | `Owner@12345` | Has no store yet — redirected straight to **Create Your Store**, ready to set one up |
| Customer | `customer_demo` | `Customer@12345` | Can browse stalls and place orders |

Log in at `/accounts/login/` with any of the above.

**Change these passwords (or delete the accounts) before deploying to production** — they're for local testing only.

## Running tests

```bash
python manage.py test
```

15 tests cover registration, RBAC/IDOR protection, stock-safe checkout, and
order merging. See `SECURITY.md` for the full security testing writeup.

## Key user flows

1. **Store owner** registers at `/accounts/register/owner/` → creates a
   store (auto-generates a QR code linking to the store's public menu, and
   lets you pick a currency — a common one like ฿/€/₹, or a fully custom
   symbol/uploaded icon) → sets operating hours → adds categories & menu
   items → configures tax rules via `/django-admin/` (TaxConfiguration) →
   manages incoming orders (Pending → **Order Received (Confirmed)** →
   Preparing → Completed/Cancelled, filterable by status/date/total), merges
   tickets, and reviews the analytics dashboard.
2. **Customer** registers at `/accounts/register/customer/` (or checks out
   as a guest) → browses `/stores/` or scans a store's QR code → adds items
   to cart (with live item pictures/prices, removable before checkout) →
   checks out → receives an order confirmation number, a **downloadable PDF
   bill**, and can **track their order status** any time at `/track-order/`
   using the order number plus the phone/email/table number they provided.
3. **Platform admin** logs in, is redirected to `/platform-admin/dashboard/`
   for a cross-platform overview, and uses `/django-admin/` for full
   user/store/order management.

### Currency

Each store picks its own currency independently under **Edit Store**:
a quick-pick list (USD, EUR, GBP, INR, THB, JPY, AUD, CAD, CNY, SGD, AED),
or **Custom**, where you supply your own text symbol (e.g. `Kč`) and/or
upload a small icon image to use in place of text. All prices throughout
that store's pages, the owner's order/analytics views, and the PDF bill use
this automatically.

### Order tracking & bills

- `/track-order/` — public page where anyone (logged in or guest) can check
  an order's status by entering the order number plus the phone, email, or
  table number used at checkout (this pairing prevents strangers from
  browsing arbitrary order numbers).
- `/my-orders/` — logged-in customers see their full order history.
- Every order has a **Download Bill (PDF)** link (order confirmation, order
  tracking, order detail, and My Orders pages) generated server-side via
  ReportLab.

## Migrating to PostgreSQL

SQLite is fine for development, but you'll want PostgreSQL for anything
real (concurrent writes, backups, multiple app instances). Switching is a
single environment variable — no code changes needed.

**If you're using Docker (recommended)** — this is handled automatically;
skip to the [Docker section](#deploying-with-docker--caddy) below.

**If you're running without Docker:**

1. Install PostgreSQL and create a database + user:
   ```bash
   sudo -u postgres psql
   ```
   ```sql
   CREATE USER yourtrolley_app WITH PASSWORD 'choose-a-strong-password';
   CREATE DATABASE yourtrolley OWNER yourtrolley_app;
   \q
   ```
2. In your `.env` (copy from `.env.example` if you haven't), set:
   ```
   DJANGO_USE_POSTGRES=True
   DJANGO_DB_NAME=yourtrolley
   DJANGO_DB_USER=yourtrolley_app
   DJANGO_DB_PASSWORD=choose-a-strong-password
   DJANGO_DB_HOST=localhost
   DJANGO_DB_PORT=5432
   ```
3. Install the Postgres driver (already in `requirements.txt`):
   ```bash
   pip install -r requirements.txt
   ```
4. Run migrations against the new database:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

That's it — `config/settings.py` reads `DJANGO_USE_POSTGRES` and switches
the `DATABASES` config automatically. If you have existing data in
`db.sqlite3` you want to carry over, dump it before switching and load it
after:
```bash
# Before switching (while DJANGO_USE_POSTGRES is still False/unset):
python manage.py dumpdata --natural-foreign --natural-primary \
  --exclude contenttypes --exclude auth.permission > backup.json

# After switching to Postgres and running migrate:
python manage.py loaddata backup.json
```

## Deploying with Docker + Caddy

The repo includes a complete, ready-to-run stack: `Dockerfile`,
`docker-compose.yml`, `docker-entrypoint.sh`, and `Caddyfile` — Django app,
PostgreSQL, and Caddy (automatic HTTPS) each in their own container.

**What each piece does:**
- **`db`** — PostgreSQL 16, with a persistent volume so data survives
  container restarts/rebuilds.
- **`app`** — builds this project, waits for Postgres to be ready, runs
  migrations and `collectstatic` automatically on every start (via
  `docker-entrypoint.sh`), then serves the app with Gunicorn on an internal
  port (never exposed directly to the internet).
- **`caddy`** — the only container with ports 80/443 open. It reverse-
  proxies everything to `app`, serves `/static/` and `/media/` directly
  from shared volumes for speed, and automatically requests + renews a
  real HTTPS certificate from Let's Encrypt for your domain.

### Steps

1. **Point your domain at the server.** Create an A record (and AAAA if
   using IPv6) for your domain pointing at the server's public IP. Caddy
   needs this to work *before* you start it, since it verifies domain
   ownership to issue the certificate.

2. **Edit the `Caddyfile`** — replace `yourtrolley.example.com` (both
   occurrences) with your real domain.

3. **Create your `.env`:**
   ```bash
   cp .env.example .env
   ```
   Edit it and set at minimum:
   - `DJANGO_SECRET_KEY` — generate one: `python -c "import secrets; print(secrets.token_urlsafe(50))"`
   - `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` — your real domain(s)
   - `DJANGO_SITE_BASE_URL` — `https://yourdomain.com` (used to build QR code links)
   - `DJANGO_DB_PASSWORD` — a strong password (used by both the `db` and `app` containers)

   You do **not** need to set `DJANGO_USE_POSTGRES` yourself here —
   `docker-compose.yml` sets it to `True` automatically for the `app`
   service.

4. **Build and start everything:**
   ```bash
   docker compose up -d --build
   ```
   First run will: build the app image, start Postgres, wait for it to
   become healthy, run migrations, collect static files, then start
   Gunicorn and Caddy. Caddy will request the HTTPS certificate on its
   first request to your domain (may take a few seconds).

5. **Create your admin account:**
   ```bash
   docker compose exec app python manage.py createsuperuser
   ```
   (Superusers automatically get the Platform Admin role — see the
   "Quick-start demo accounts" section above for the underlying behavior.)

6. **Visit `https://yourdomain.com`** — you should see the live site with
   a valid HTTPS certificate, no manual certificate setup required.

### Useful commands once running

```bash
docker compose logs -f app          # tail the Django/Gunicorn logs
docker compose logs -f caddy        # tail Caddy's access/cert logs
docker compose exec app python manage.py <any management command>
docker compose exec db psql -U yourtrolley_app -d yourtrolley   # DB shell
docker compose down                 # stop everything (data volumes persist)
docker compose up -d --build        # rebuild + restart after a code change
```

### Backups

Postgres data lives in the `postgres_data` Docker volume. To back it up:
```bash
docker compose exec db pg_dump -U yourtrolley_app yourtrolley > backup_$(date +%F).sql
```
To restore:
```bash
cat backup_2026-07-29.sql | docker compose exec -T db psql -U yourtrolley_app -d yourtrolley
```

### Running without Docker

If you'd rather not use Docker, follow the "Migrating to PostgreSQL"
section above, then run Caddy directly on the host — see the comment block
at the bottom of the `Caddyfile` for the two lines to change (it points at
`app:8000` for Docker by default; switch that to `127.0.0.1:8000` and run
Gunicorn yourself):
```bash
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
```

## Security

See `SECURITY.md` for a full breakdown of how SQL injection, CSRF, XSS,
authentication/authorization (RBAC + IDOR protection), file-upload
validation, and race-condition safety were implemented and tested.
