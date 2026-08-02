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

The app ships with **SQLite active by default** (see `config/settings.py`)
— zero setup, fine for development and small deployments. A complete
PostgreSQL configuration is included right below it, **commented out**,
for whenever you're ready for something more production-grade (concurrent
writes, proper backups, running multiple app instances).

**To switch:**

1. Install PostgreSQL and create a database + user:
   ```bash
   sudo -u postgres psql
   ```
   ```sql
   CREATE USER yourtrolley_app WITH PASSWORD 'choose-a-strong-password';
   CREATE DATABASE yourtrolley OWNER yourtrolley_app;
   \q
   ```
2. In `config/settings.py`, comment out the **ACTIVE: SQLite** block and
   uncomment the **PRODUCTION: PostgreSQL** block right below it.
3. In your `.env` (copy from `.env.example` if you haven't), set:
   ```
   DJANGO_DB_NAME=yourtrolley
   DJANGO_DB_USER=yourtrolley_app
   DJANGO_DB_PASSWORD=choose-a-strong-password
   DJANGO_DB_HOST=localhost
   DJANGO_DB_PORT=5432
   ```
4. Install dependencies (the Postgres driver, `psycopg2-binary`, is
   already listed in `requirements.txt`) and migrate:
   ```bash
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py createsuperuser
   ```

If you have existing data in `db.sqlite3` you want to carry over, dump it
**before** switching and load it after:
```bash
# Before switching (SQLite still active):
python manage.py dumpdata --natural-foreign --natural-primary \
  --exclude contenttypes --exclude auth.permission > backup.json

# After switching to Postgres and running migrate:
python manage.py loaddata backup.json
```

## Deploying with Docker + Caddy

The repo includes a ready-to-run stack using **SQLite** by default:
`Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`, and
`Caddyfile` — the Django app and Caddy (automatic HTTPS) each in their own
container. No separate database container is needed for SQLite.

**What each piece does:**
- **`app`** — builds this project, runs migrations and `collectstatic`
  automatically on every start (via `docker-entrypoint.sh`), then serves
  the app with Gunicorn on an internal port (never exposed directly to the
  internet). The SQLite database file is bind-mounted from the host so
  your data survives container rebuilds.
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

4. **Create the SQLite file on the host** so Docker can bind-mount it
   correctly as a file (important — skipping this step causes Docker to
   create a *directory* named `db.sqlite3` instead, which will break the
   app):
   ```bash
   touch db.sqlite3
   ```

5. **Build and start everything:**
   ```bash
   docker compose up -d --build
   ```
   First run will: build the app image, run migrations, collect static
   files, then start Gunicorn and Caddy. Caddy will request the HTTPS
   certificate on its first request to your domain (may take a few
   seconds).

6. **Create your admin account:**
   ```bash
   docker compose exec app python manage.py createsuperuser
   ```
   (Superusers automatically get the Platform Admin role — see the
   "Quick-start demo accounts" section above for the underlying behavior.)

7. **Visit `https://yourdomain.com`** — you should see the live site with
   a valid HTTPS certificate, no manual certificate setup required.

### Useful commands once running

```bash
docker compose logs -f app          # tail the Django/Gunicorn logs
docker compose logs -f caddy        # tail Caddy's access/cert logs
docker compose exec app python manage.py <any management command>
docker compose down                 # stop everything (db.sqlite3 + volumes persist)
docker compose up -d --build        # rebuild + restart after a code change
```

### Backups

With SQLite, your entire database is just the `db.sqlite3` file sitting
next to `docker-compose.yml` on the host — back it up like any other file:
```bash
cp db.sqlite3 backup_$(date +%F).sqlite3
```

### Switching this Docker setup to PostgreSQL

If you later want Postgres in the Docker stack too:

1. Follow the "Migrating to PostgreSQL" steps above to uncomment the
   Postgres block in `config/settings.py`.
2. Add a `db` service back to `docker-compose.yml`:
   ```yaml
   services:
     db:
       image: postgres:16-alpine
       restart: unless-stopped
       environment:
         POSTGRES_DB: ${DJANGO_DB_NAME}
         POSTGRES_USER: ${DJANGO_DB_USER}
         POSTGRES_PASSWORD: ${DJANGO_DB_PASSWORD}
       volumes:
         - postgres_data:/var/lib/postgresql/data
       healthcheck:
         test: ["CMD-SHELL", "pg_isready -U ${DJANGO_DB_USER}"]
   ```
   Then add `depends_on: db` and `environment: {DJANGO_DB_HOST: db}` to the
   `app` service, remove the `./db.sqlite3:/app/db.sqlite3` volume line
   (no longer needed), and add `postgres_data:` under the top-level
   `volumes:` section.
3. Add a short wait-for-Postgres step at the top of
   `docker-entrypoint.sh` (before `migrate` runs) so the app container
   doesn't start before the `db` container is ready to accept connections.

### Running without Docker

If you'd rather not use Docker, run Caddy directly on the host — see the
comment block at the bottom of the `Caddyfile` for the two lines to change
(it points at `app:8000` for Docker by default; switch that to
`127.0.0.1:8000`) and run Gunicorn yourself:
```bash
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
```

## Security

See `SECURITY.md` for a full breakdown of how SQL injection, CSRF, XSS,
authentication/authorization (RBAC + IDOR protection), file-upload
validation, and race-condition safety were implemented and tested.
