"""
Lightweight brute-force protection for the login endpoint, built on
Django's cache framework (no extra dependency required).

Two independent counters are tracked:
  * Per (IP, username) -- stops repeated guessing against one specific
    account.
  * Per IP across all usernames -- stops a single attacker spraying many
    different usernames/passwords (credential stuffing) from one source.

In production, point CACHES at Redis or Memcached (see config/settings.py)
so lockout state is shared across all Gunicorn worker processes -- the
default LocMemCache used in local development is per-process only.
"""

from django.core.cache import cache

MAX_ATTEMPTS_PER_ACCOUNT = 5   # failed attempts against one username from one IP
MAX_ATTEMPTS_PER_IP = 20       # failed attempts against ANY username from one IP
LOCKOUT_SECONDS = 15 * 60      # 15 minutes


def get_client_ip(request) -> str:
    """
    Best-effort real client IP.

    This trusts X-Forwarded-For because the application is documented to
    always run behind Caddy (see Caddyfile), which sets that header itself
    and is the only thing expected to reach Django directly. If you ever
    expose Django directly to the internet WITHOUT a trusted reverse proxy
    in front, switch this to request.META.get("REMOTE_ADDR") only --
    otherwise an attacker could spoof the header to dodge IP-based lockouts.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _account_key(ip: str, username: str) -> str:
    return f"loginattempts:account:{ip}:{username.strip().lower()}"


def _ip_key(ip: str) -> str:
    return f"loginattempts:ip:{ip}"


def is_locked_out(request, username: str) -> bool:
    ip = get_client_ip(request)
    account_attempts = cache.get(_account_key(ip, username), 0)
    ip_attempts = cache.get(_ip_key(ip), 0)
    return account_attempts >= MAX_ATTEMPTS_PER_ACCOUNT or ip_attempts >= MAX_ATTEMPTS_PER_IP


def register_failed_attempt(request, username: str) -> tuple[int, int]:
    """Increments both counters (sliding LOCKOUT_SECONDS window) and returns (account_attempts, ip_attempts)."""
    ip = get_client_ip(request)

    account_key = _account_key(ip, username)
    account_attempts = cache.get(account_key, 0) + 1
    cache.set(account_key, account_attempts, timeout=LOCKOUT_SECONDS)

    ip_key = _ip_key(ip)
    ip_attempts = cache.get(ip_key, 0) + 1
    cache.set(ip_key, ip_attempts, timeout=LOCKOUT_SECONDS)

    return account_attempts, ip_attempts


def clear_attempts(request, username: str) -> None:
    """Called on a successful login to un-penalize that specific account immediately."""
    ip = get_client_ip(request)
    cache.delete(_account_key(ip, username))
    # Deliberately NOT clearing the per-IP counter on success -- a
    # successful login for one account shouldn't reset an attacker's
    # per-IP spray-attempt counter built up against other usernames.
