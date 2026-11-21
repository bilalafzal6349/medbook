"""One small database layer for SQLite (tests, laptop demo) and PostgreSQL (deployment).

    DATABASE_URL=postgresql://medbook:medbook@localhost:5432/medbook   -> PostgreSQL (connection pool)
    DATABASE_URL unset                                                 -> SQLite file at MEDBOOK_DB

All SQL in clinic_db.py and reminders.py is written once, with `?` placeholders, in the subset that both
engines accept. This module turns `?` into `%s` for PostgreSQL, turns date/datetime parameters into ISO
strings for SQLite, and returns every row as a plain dict.

Concurrency
    PostgreSQL: each call borrows a pooled connection; `transaction()` holds one connection for a whole
    read-check-write, so `SELECT ... FOR UPDATE` row locks work (see Clinic.book).
    SQLite: one shared connection guarded by a lock, so threads (FastAPI's thread pool) never interleave.
"""
import atexit
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

try:   # only needed for PostgreSQL
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except ImportError:   # pragma: no cover - SQLite-only install
    psycopg = None

INTEGRITY_ERRORS = (sqlite3.IntegrityError,) + ((psycopg.IntegrityError,) if psycopg else ())


def _sqlite_param(v):
    if isinstance(v, datetime):
        return v.isoformat(timespec="seconds")
    if isinstance(v, date):
        return v.isoformat()
    return v


class _Tx:
    """What a transaction body sees: q() for reads, run() for writes, both on the same connection."""

    def __init__(self, db, con):
        self.db, self.con = db, con

    def q(self, sql, params=()):
        cur = self.con.execute(self.db._sql(sql), self.db._params(params))
        return [dict(r) for r in cur.fetchall()] if cur.description else []

    def one(self, sql, params=()):
        rows = self.q(sql, params)
        return rows[0] if rows else None

    def run(self, sql, params=()):
        return self.con.execute(self.db._sql(sql), self.db._params(params)).rowcount


class Database:
    def __init__(self, url=None, sqlite_path=None):
        url = url if url is not None else os.environ.get("DATABASE_URL", "")
        if url.startswith(("postgres://", "postgresql://")):
            if psycopg is None:
                raise RuntimeError('DATABASE_URL is PostgreSQL but psycopg is missing: pip install "psycopg[binary]" psycopg_pool')
            self.kind = "postgres"
            self.url = url
            self.pool = ConnectionPool(url, min_size=1, max_size=int(os.environ.get("MEDBOOK_DB_POOL", "10")),
                                       kwargs={"row_factory": dict_row, "autocommit": False}, open=True)
            self.pool.wait(timeout=30)
            atexit.register(self.pool.close)
        else:
            self.kind = "sqlite"
            p = Path(sqlite_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            self.url = str(p)
            self._con = sqlite3.connect(p, check_same_thread=False, isolation_level=None)   # explicit BEGIN/COMMIT
            self._con.row_factory = sqlite3.Row
            self._con.execute("PRAGMA foreign_keys = ON")
            self._lock = threading.RLock()

    # ------------------------------------------------------------------ helpers
    def _sql(self, sql):
        return sql.replace("?", "%s") if self.kind == "postgres" else sql

    def _params(self, params):
        return tuple(params) if self.kind == "postgres" else tuple(_sqlite_param(v) for v in params)

    def describe(self):
        if self.kind == "postgres":
            return "postgresql://" + self.url.rsplit("@", 1)[-1]   # never print the password
        return f"sqlite:{self.url}"

    # ------------------------------------------------------------------ API
    @contextmanager
    def transaction(self, write=True):
        if self.kind == "postgres":
            with self.pool.connection() as con:   # commits on success, rolls back on exception
                yield _Tx(self, con)
        else:
            with self._lock:
                self._con.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                try:
                    yield _Tx(self, self._con)
                except BaseException:
                    self._con.execute("ROLLBACK")
                    raise
                self._con.execute("COMMIT")

    def q(self, sql, params=()):
        with self.transaction(write=False) as tx:
            return tx.q(sql, params)

    def one(self, sql, params=()):
        rows = self.q(sql, params)
        return rows[0] if rows else None

    def run(self, sql, params=()):
        with self.transaction() as tx:
            return tx.run(sql, params)

    def script(self, sql):
        """Run several ;-separated statements (schema creation)."""
        with self.transaction() as tx:
            for stmt in (s.strip() for s in sql.split(";")):
                if stmt:
                    tx.run(stmt)

    def drop_all(self, tables):
        with self.transaction() as tx:
            for t in tables:
                tx.run(f"DROP TABLE IF EXISTS {t}" + (" CASCADE" if self.kind == "postgres" else ""))

    def close(self):
        if self.kind == "postgres":
            self.pool.close()
        else:
            self._con.close()
