"""Build a hosted database (e.g. Supabase) interactively, without secrets in files or history.

Usage (from the repo root):  uv run --project backend python -m data.setup_remote

Asks for the connection string (with [YOUR-PASSWORD] in it) and the database password
(hidden), generates a strong password for the read-only role, builds everything with
data.setup_db, checks the read-only login works, and prints DATABASE_URL_RO for the API host.
"""
import getpass
import os
import secrets
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg

PLACEHOLDER = "[YOUR-PASSWORD]"


def build_urls(template: str, admin_password: str, ro_password: str) -> tuple[str, str]:
    """Admin URL from the template; read-only URL with the same host and user suffix.

    Supabase's pooler user names look like "postgres.<project-ref>", so the read-only user
    becomes "analyst_ro.<project-ref>"; a plain "postgres" user becomes "analyst_ro".
    """
    admin = template.replace(PLACEHOLDER, quote(admin_password, safe=""))
    parts = urlsplit(admin)
    user = parts.username or "postgres"
    ro_user = "analyst_ro" + user[len("postgres"):] if user.startswith("postgres") else "analyst_ro"
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    ro = urlunsplit((parts.scheme, f"{ro_user}:{quote(ro_password, safe='')}@{host}",
                     parts.path, parts.query, ""))
    return admin, ro


def main() -> None:
    template = input(f"Paste the connection string (keep {PLACEHOLDER} in it): ").strip()
    if PLACEHOLDER not in template:
        raise SystemExit(f"The string must still contain {PLACEHOLDER}.")
    admin_password = getpass.getpass("Database password (typing is hidden): ")
    ro_password = secrets.token_urlsafe(24)
    admin_url, ro_url = build_urls(template, admin_password, ro_password)

    os.environ["DATABASE_URL_ADMIN"] = admin_url
    os.environ["ANALYST_RO_PASSWORD"] = ro_password
    from data.setup_db import main as setup_db  # reads the variables set above
    print("Building the database (about a minute)...")
    setup_db()

    with psycopg.connect(ro_url) as conn:
        (orders,) = conn.execute("SELECT COUNT(*) FROM orders").fetchone()
    print(f"Read-only login works ({orders} orders visible).\n")
    print("Save this somewhere safe. It's DATABASE_URL_RO for Render:\n")
    print(ro_url)


if __name__ == "__main__":
    main()
