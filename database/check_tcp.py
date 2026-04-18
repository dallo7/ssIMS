"""
Verify TCP reachability to Postgres (RDS) using the same .env as the app.

A timeout here means the problem is network / AWS security — not SQLAlchemy or wrong password
(Postgres is never reached, so authentication never runs).

Usage (from project root):
  python -m database.check_tcp
"""
from __future__ import annotations

import socket
import sys


def main() -> int:
    from database.engine import _bootstrap_env_file, _ensure_dotenv, _merge_env_file, _project_root

    _bootstrap_env_file()
    root = _project_root()
    _merge_env_file(root / ".env")
    _merge_env_file(root / ".env.local")
    _ensure_dotenv()

    import os

    host = (os.environ.get("CPI_PG_HOST") or "").strip()
    port_raw = (os.environ.get("CPI_PG_PORT") or "5432").strip()
    if not host:
        print("Set CPI_PG_HOST (or CPI_DATABASE_URL) in .env", file=sys.stderr)
        return 2
    try:
        port = int(port_raw)
    except ValueError:
        port = 5432

    print(f"Opening TCP socket to {host!r} port {port} (5s timeout)...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5.0)
    try:
        s.connect((host, port))
    except OSError as e:
        print(f"FAILED: {e}")
        print(
            "\nFix on AWS (typical): RDS instance -> Modify -> Publicly accessible = Yes; "
            "VPC security group -> Inbound -> PostgreSQL TCP 5432 from your public IP /32 "
            "(or VPN CIDR). Then: Test-NetConnection <host> -Port 5432 -> TcpTestSucceeded : True"
        )
        return 1
    finally:
        try:
            s.close()
        except OSError:
            pass

    print("OK — TCP port is reachable from this PC. If the app still fails, check sslmode, user, password, and DB name.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
