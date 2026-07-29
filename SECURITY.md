# Security & Vulnerability Testing Documentation

This document explains how each OWASP Top 10 concern from the project brief
was implemented and how it was tested. All items below were exercised
against the actual codebase during development (see `accounts/tests.py`,
`stores/tests.py`, `orders/tests.py` for the automated regression suite).

## 1. SQL Injection (SQLi)

**Implementation**
- Every database query in the project goes through the Django ORM
  (`Model.objects.filter(...)`, `get_object_or_404(...)`, aggregation via
  `Sum`/`F`/`Count` in `analytics/views.py`). No `.raw()`, no
  `cursor.execute()` with string-formatted SQL, and no f-string/`%`-built
  queries anywhere in the codebase.
- User-supplied search input (`stores/views.py::store_list`, the `q` query
  parameter) is passed to `.filter(name__icontains=query)`, which uses
  parameter binding — the ORM sends the value as a bound parameter, not as
  concatenated SQL text.

**Testing performed**
- Manually submitted classic SQLi payloads (`' OR '1'='1`, `'; DROP TABLE
  stores_store;--`) into the store search box and every text form field;
  all were treated as literal search/text values with no error or data
  leakage.
- Verified with `python manage.py shell` that `Store.objects.filter(name__icontains="x' OR '1'='1")`
  produces a correctly parameterized query via `.query` inspection.

## 2. Cross-Site Request Forgery (CSRF)

**Implementation**
- `django.middleware.csrf.CsrfViewMiddleware` is enabled globally in
  `MIDDLEWARE` (config/settings.py) and is never excluded on any view.
- Every `<form method="post">` in the templates includes `{% csrf_token %}`
  (login, registration, store/category/item CRUD, checkout, cart, order
  status updates, order merge, logout).
- `CSRF_COOKIE_SAMESITE = "Lax"` and, in production (`DEBUG=False`),
  `CSRF_COOKIE_SECURE = True` so the CSRF cookie is never sent over plain
  HTTP or cross-site in a way that could be replayed.

**Testing performed**
- Confirmed that POST requests submitted with the `csrfmiddlewaretoken`
  field stripped are rejected with HTTP 403 by Django's CSRF middleware.
- Confirmed the token is rotated per session and tied to the session cookie.

## 3. Cross-Site Scripting (XSS)

**Implementation**
- All templates use Django's default template auto-escaping; no template
  in the project uses `|safe` or `{% autoescape off %}` on user-controlled
  content. The one exception is the analytics dashboard's Chart.js payload
  (`analytics/dashboard.html`), which is server-generated JSON of
  aggregated numbers/labels (never raw user HTML) and is inserted using
  `|escapejs` specifically to prevent breaking out of the `<script>` string
  context.
- Store names, descriptions, food item names/descriptions, and order
  contact fields are all rendered through `{{ variable }}`, which HTML-
  escapes `<`, `>`, `&`, `"`, `'` automatically.
- Uploaded images are re-encoded through Pillow (`stores/utils.py`) rather
  than served as-uploaded, which strips any embedded scripts/metadata and
  rejects non-image payloads (see "File upload security" below).

**Testing performed**
- Submitted `<script>alert(1)</script>` and `<img src=x onerror=alert(1)>`
  into store name, description, food item name/description, and category
  name fields; confirmed they render as literal escaped text in the browser
  (view-source shows `&lt;script&gt;`), not as executable markup.

## 4. Authentication & Authorization

**Implementation**
- Passwords are hashed with Argon2 (`PASSWORD_HASHERS`, Argon2 first) —
  memory-hard and resistant to GPU/ASIC cracking, with PBKDF2 as a
  compatibility fallback. Raw passwords are never logged or stored.
- `AUTH_PASSWORD_VALIDATORS` enforces minimum length (9), rejects common
  passwords, purely numeric passwords, and passwords too similar to the
  user's own username/email.
- **Role-Based Access Control (RBAC)** is enforced in two independent
  layers (defence-in-depth):
  1. `accounts/middleware.py::RoleBasedAccessMiddleware` blocks any request
     to `/owner/*` or `/platform-admin/*` paths before the view executes,
     unless the logged-in user has the matching `role`.
  2. Every owner-facing view additionally calls `_require_owner_of(request,
     store)` (see `stores/views.py`, `orders/views.py`), which checks that
     `store.owner_id == request.user.id` for the *specific* object being
     accessed. This is what stops "Owner A" from editing "Owner B"'s store
     even though both hold the `OWNER` role — layer 1 alone would not catch
     this class of bug (an Insecure Direct Object Reference).
  3. Every `get_object_or_404()` call for a Category, FoodItem, or Order is
     scoped with `store=store` (or reached via the store's own owner check),
     so a crafted primary key belonging to another store can never be
     fetched, edited, or deleted from an owner's management pages.

**Testing performed**
- Automated test: registered two separate owner accounts, each with their
  own store, and confirmed Owner B receives HTTP 403 when requesting Owner
  A's store-edit, item-edit, and order-detail URLs directly by ID/slug.
- Confirmed an anonymous or CUSTOMER-role user is redirected away from any
  `/owner/` or `/platform-admin/` URL.
- Confirmed failed logins are logged (`accounts` logger) without revealing
  whether the username or password was the incorrect field (generic error
  message from Django's `AuthenticationForm`).

## 5. File upload security

- `stores/utils.py::validate_and_process_image` rejects any file whose
  extension isn't in `ALLOWED_IMAGE_EXTENSIONS`, enforces a hard size cap
  (`MAX_UPLOAD_IMAGE_MB`), and — critically — opens the file with Pillow and
  calls `.verify()` before ever using it. A file with a `.jpg` extension
  that is actually a script or other executable content fails Pillow's
  validation and is rejected with a clean `ValidationError` rather than
  being written to disk.
- All accepted images are re-encoded to JPEG server-side (not just renamed),
  which also strips EXIF metadata and any format-specific embedded scripts
  (e.g. malformed SVG/PNG polyglots).
- Generated filenames use `uuid4()`, never the client-supplied filename, so
  path traversal (`../../etc/passwd`) and null-byte tricks in filenames are
  structurally impossible.

## 6. Broken access control / IDOR (general)

Beyond the RBAC section above, every foreign-keyed lookup in owner and
checkout views is scoped to the correct parent object:
- Checkout (`orders/views.py::checkout`) re-fetches each `FoodItem` scoped
  to `store=store`, so a tampered cart cookie referencing another store's
  item ID cannot be checked out against the wrong store.
- `OrderMergeForm` restricts its queryset to the requesting owner's own
  store and excludes already-merged/completed/cancelled orders, and
  `orders/services.py::merge_orders` re-validates store ownership and order
  state server-side even if the form were bypassed.

## 7. Session & transport security

- `SESSION_COOKIE_HTTPONLY = True` (JS cannot read the session cookie).
- In production (`DEBUG=False`): `SESSION_COOKIE_SECURE`,
  `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`, and HSTS are all enabled.
  Caddy terminates TLS and forwards `X-Forwarded-Proto`, which Django is
  configured to trust via `SECURE_PROXY_SSL_HEADER`.
- `X_FRAME_OPTIONS = "DENY"` and `SECURE_CONTENT_TYPE_NOSNIFF = True`
  mitigate clickjacking and MIME-sniffing attacks respectively.

## 8. Race conditions (business-logic integrity)

- `orders/services.py::create_order_with_items` uses
  `FoodItem.objects.select_for_update()` inside a `transaction.atomic()`
  block, so two customers checking out the last unit of an item
  simultaneously cannot both succeed — the second request will see the
  updated (locked) stock count and fail cleanly with a "not enough stock"
  message instead of overselling.

## 9. Logging & auditability

- Failed logins, cross-tenant access attempts (blocked IDOR/RBAC attempts),
  order status changes, and order placement are all logged via Python's
  `logging` module to a rotating file (`logs/security.log`) as configured
  in `LOGGING` (config/settings.py), enabling later audit or intrusion
  detection.

## 10. Brute-force / credential-stuffing protection (login lockout)

**Implementation** (`accounts/throttling.py`, wired into `accounts/views.py::RoleAwareLoginView`)

- Two independent counters are tracked via Django's cache framework on every
  failed login POST:
  - **Per (IP, username):** locks out after **5** failed attempts against
    one specific account from one IP — stops targeted password guessing.
  - **Per IP, across all usernames:** locks out after **20** failed
    attempts from one IP regardless of which username was tried — stops
    credential-stuffing / username-spraying from a single source.
- Both counters use a **15-minute sliding lockout window** (`LOCKOUT_SECONDS`).
  Once locked out, the endpoint returns **HTTP 429** and refuses to even
  check the password — including the *correct* password — until the window
  expires, so an attacker can't distinguish "wrong password" from "right
  password, but locked out."
- A successful login clears that specific account's counter immediately
  (but deliberately leaves the per-IP counter alone, so a successful login
  on one account doesn't reset an attacker's spray-attempt budget against
  other accounts from the same IP).
- All failed attempts and lockout triggers are logged (`accounts` logger)
  with the attempt counts, for later audit/alerting.
- **Production note:** the default cache backend (`LocMemCache`) is
  per-process, so if you run multiple Gunicorn workers, lockout counters
  won't be shared between them. `config/settings.py` includes a commented
  Redis `CACHES` block — switch to it (via `django-redis`) in production so
  lockout state is consistent across all workers.

**Testing performed**

- Automated tests (`accounts/tests.py::BruteForceLockoutTests`) confirm:
  5 failed attempts against one account triggers a 429 on the 6th attempt
  *even with the correct password*; a successful login clears that
  account's own counter; and 20 failed attempts across different usernames
  from one IP triggers the IP-wide lockout.
- Manually verified against a running server with `curl`: 5 wrong-password
  POSTs each return 200 (normal invalid-login response), the 6th returns
  429, and submitting the genuinely correct password while locked out
  still returns 429 rather than logging in.

## Running the test suite

```bash
python manage.py test
```

The suite (accounts/tests.py, stores/tests.py, orders/tests.py) covers:
registration & login, unique store-name enforcement, CSRF-token
requirement on POST endpoints, cross-tenant IDOR attempts on store/item/
order endpoints (expect 403), stock-safe checkout, and order-merge totals.
