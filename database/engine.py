import os
import shutil
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

_dotenv_loaded = False


def _project_root() -> Path:
    """Folder that contains `app.py` (works from `database/` or nested package layouts)."""
    p = Path(__file__).resolve().parent.parent
    if (p / "app.py").is_file():
        return p
    pp = p.parent
    if (pp / "app.py").is_file():
        return pp
    return p


def _bootstrap_env_file() -> None:
    """If `.env` is missing, copy `.env.example` so first run has a working local URL."""
    root = _project_root()
    env_path = root / ".env"
    example = root / ".env.example"
    if not env_path.exists() and example.is_file():
        shutil.copyfile(example, env_path)


def _merge_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs without python-dotenv (optional dependency)."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key or val == "":
            continue
        # Do not override non-empty values (shell env or earlier files win).
        if (os.environ.get(key) or "").strip():
            continue
        os.environ[key] = val


def _ensure_dotenv() -> None:
    """Load `.env` from the project root (not only cwd — fixes PyCharm / other launch cwd)."""
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    try:
        from dotenv import load_dotenv

        root = _project_root()
        # Later calls with override=False do not replace vars already exported in the shell.
        load_dotenv(root / ".env")
        load_dotenv(root / ".env.local")
        load_dotenv()  # cwd fallback
    except ImportError:
        pass


def _default_sqlite_path() -> Path:
    """Location for the SQLite fallback DB. Override with CPI_SQLITE_PATH."""
    override = (os.environ.get("CPI_SQLITE_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    # Persistent disks on Render/Fly/Railway are typically mounted at /data.
    data_dir = Path("/data") if Path("/data").is_dir() else _project_root() / "data"
    return (data_dir / "cpi_inventory.sqlite").resolve()


def _database_url() -> str | None:
    """Resolve the SQLAlchemy URL.

    Priority:
      1. CPI_DATABASE_URL / DATABASE_URL (or CPI_DATABASE_URL_FILE).
      2. Discrete CPI_PG_* variables (PostgreSQL / RDS).
      3. SQLite fallback — always on, so the app boots even without credentials.
         Path comes from CPI_SQLITE_PATH, else `/data/cpi_inventory.sqlite`
         (persistent disk on Render/Fly), else `<project>/data/cpi_inventory.sqlite`.
    """
    # Docker / k8s: URL in a file (e.g. Docker secrets mount).
    url_file = (os.environ.get("CPI_DATABASE_URL_FILE") or "").strip()
    if url_file and not (os.environ.get("CPI_DATABASE_URL") or os.environ.get("DATABASE_URL")):
        p = Path(url_file).expanduser()
        if p.is_file():
            raw = p.read_text(encoding="utf-8").strip()
            if raw:
                os.environ["CPI_DATABASE_URL"] = raw

    url = (os.environ.get("CPI_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        from database.pg_url import build_sqlalchemy_url_from_pg_env

        url = build_sqlalchemy_url_from_pg_env() or ""
    if not url:
        sqlite_path = _default_sqlite_path()
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{sqlite_path.as_posix()}"
    if url.startswith("postgres://"):
        # Heroku-style alias; SQLAlchemy expects postgresql://
        url = "postgresql://" + url[len("postgres://") :]
    return url


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite:") or url.startswith("sqlite+")


DB_PATH = None  # no SQLite file backups in Postgres mode
_engine = None
_SessionLocal = None


def _db_connect_timeout_sec() -> int:
    raw = (
        os.environ.get("CPI_PG_CONNECT_TIMEOUT") or os.environ.get("CPI_DB_CONNECT_TIMEOUT") or "15"
    ).strip()
    try:
        n = int(raw)
    except ValueError:
        return 15
    return max(1, min(n, 120))


def _pool_settings() -> dict:
    try:
        pool_size = int((os.environ.get("CPI_PG_POOL_SIZE") or "5").strip())
    except ValueError:
        pool_size = 5
    try:
        max_overflow = int((os.environ.get("CPI_PG_MAX_OVERFLOW") or "10").strip())
    except ValueError:
        max_overflow = 10
    try:
        pool_timeout = int((os.environ.get("CPI_PG_POOL_TIMEOUT") or "30").strip())
    except ValueError:
        pool_timeout = 30
    pool_size = max(1, min(pool_size, 50))
    max_overflow = max(0, min(max_overflow, 50))
    pool_timeout = max(5, min(pool_timeout, 120))
    return {
        "pool_size": pool_size,
        "max_overflow": max_overflow,
        "pool_timeout": pool_timeout,
    }


def get_engine():
    global _engine
    if _engine is None:
        _bootstrap_env_file()
        root = _project_root()
        _merge_env_file(root / ".env")
        _merge_env_file(root / ".env.local")
        if not _database_url():
            _merge_env_file(root / ".env.example")
        _ensure_dotenv()
        url = _database_url()
        if not url:
            raise RuntimeError(
                "No database URL could be resolved. Set CPI_DATABASE_URL, the discrete "
                "CPI_PG_* variables, or CPI_SQLITE_PATH."
            )

        if _is_sqlite_url(url):
            # SQLite (quick deploy / dev). Enable shared cache across threads so
            # gunicorn workers + Dash background callbacks can share the connection.
            _engine = create_engine(
                url,
                echo=False,
                future=True,
                connect_args={"check_same_thread": False, "timeout": 30},
            )
            # Pragmas for durability + concurrency. WAL lets readers run while a
            # writer holds the lock — important for an API + Dash UI on one DB.
            try:
                from sqlalchemy import event

                @event.listens_for(_engine, "connect")
                def _sqlite_pragmas(dbapi_conn, _rec):  # pragma: no cover
                    cur = dbapi_conn.cursor()
                    cur.execute("PRAGMA journal_mode=WAL")
                    cur.execute("PRAGMA synchronous=NORMAL")
                    cur.execute("PRAGMA foreign_keys=ON")
                    cur.execute("PRAGMA busy_timeout=30000")
                    cur.close()
            except Exception:
                pass
        else:
            try:
                import psycopg  # noqa: F401 — driver for postgresql+psycopg:// URLs
            except ModuleNotFoundError as e:
                raise RuntimeError(
                    "The `psycopg` package is not installed in this Python environment.\n"
                    "Run (use the same interpreter as `python app.py`):\n"
                    "  python -m pip install -r requirements.txt\n"
                    "Or: python -m pip install \"psycopg[binary]==3.2.9\""
                ) from e
            pool = _pool_settings()
            _engine = create_engine(
                url,
                pool_pre_ping=True,
                echo=False,
                pool_size=pool["pool_size"],
                max_overflow=pool["max_overflow"],
                pool_timeout=pool["pool_timeout"],
                connect_args={"connect_timeout": _db_connect_timeout_sec()},
            )

    return _engine


def dispose_engine() -> None:
    """Close pooled connections (call on FastAPI shutdown / process exit)."""
    global _engine, _SessionLocal
    eng = _engine
    _engine = None
    _SessionLocal = None
    if eng is not None:
        eng.dispose()


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )
    return _SessionLocal


class _SessionCtx:
    def __init__(self):
        self._s: Session | None = None

    def __enter__(self) -> Session:
        self._s = get_session_factory()()
        return self._s

    def __exit__(self, exc_type, exc, tb):
        if self._s is None:
            return
        try:
            if exc_type is None:
                self._s.commit()
            else:
                self._s.rollback()
        finally:
            self._s.close()


def db_session() -> _SessionCtx:
    return _SessionCtx()


def init_database():
    from database import models  # noqa: F401 — register mappers
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    eng = get_engine()
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        models.Base.metadata.create_all(bind=eng)
    except OperationalError as e:
        try:
            safe = eng.url.render_as_string(hide_password=True)
        except Exception:
            safe = "(unable to format database URL)"
        if _is_sqlite_url(str(eng.url)):
            raise RuntimeError(
                f"Cannot open SQLite database at {safe}. Check that the parent "
                "directory exists, is writable by the process, and (on "
                "Render/Fly) that the persistent disk is mounted."
            ) from e
        host_hint = ""
        try:
            if (eng.url.host or "").strip().lower() == "db":
                host_hint = (
                    "\n  • Hostname `db` is usually a private container DNS name. "
                    "From your PC use the real RDS endpoint or `127.0.0.1` for local Postgres.\n"
                )
        except Exception:
            pass
        raise RuntimeError(
            "Cannot connect to PostgreSQL (timed out or refused). Check:\n"
            f"  • Attempting: {safe}\n"
            "  • From PowerShell: `Test-NetConnection <host> -Port <port>` — if TcpTestSucceeded is False, "
            "traffic never reaches Postgres (firewall, RDS not public, or wrong security group). Credentials are irrelevant until this is True.\n"
            "  • AWS RDS: instance must be Publicly accessible = Yes (if you connect from the internet); "
            "VPC security group inbound rule: PostgreSQL (5432) from your current public IP (or VPN/bastion CIDR).\n"
            "  • Local Postgres: host 127.0.0.1 and service listening on the port in your URL.\n"
            "  • If the network path is slow only: raise `CPI_PG_CONNECT_TIMEOUT` / `CPI_DB_CONNECT_TIMEOUT` in `.env` (seconds, max 120).\n"
            f"{host_hint}"
            "  • Same Python has the driver: `python -m pip install -r requirements.txt`\n"
            f"Underlying error: {e}"
        ) from e
