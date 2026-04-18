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
        load_dotenv(root / ".env")
        load_dotenv(root / ".env.local")
        load_dotenv()
    except ImportError:
        pass


def _database_url() -> str | None:
    """Required SQLAlchemy URL for PostgreSQL."""
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
        return None
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


DB_PATH = None
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
                "PostgreSQL is required. Either set CPI_DATABASE_URL (or DATABASE_URL), e.g.\n"
                "  postgresql+psycopg://user:pass@host:5432/dbname?sslmode=require\n"
                "or set discrete variables: CPI_PG_HOST, CPI_PG_PORT, CPI_PG_USER, CPI_PG_PASSWORD, CPI_PG_DB "
                "(optional CPI_PG_SSLMODE, CPI_PG_POOL_SIZE, … — see `.env.example`).\n"
                f"A starter `{root / '.env'}` is created from `.env.example` on first run when missing."
            )
        try:
            import psycopg  # noqa: F401
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
            "  • From PowerShell: `Test-NetConnection <host> -Port <port>` (should show TcpTestSucceeded : True)\n"
            "  • Postgres is running and reachable from this machine\n"
            "  • Cloud/RDS: security group allows your IP; URL usually needs `?sslmode=require`\n"
            "  • If timeouts are too tight: set CPI_DB_CONNECT_TIMEOUT=60 in `.env`\n"
            f"{host_hint}"
            "  • Same Python has the driver: `python -m pip install -r requirements.txt`\n"
            f"Underlying error: {e}"
        ) from e
