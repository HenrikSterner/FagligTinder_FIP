import os
import sqlite3
import time
from contextlib import contextmanager

import streamlit as st

try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
except Exception:
    psycopg2 = None


def _get_database_url() -> str | None:
    try:
        from_secrets = st.secrets.get("database_url")
    except Exception:
        from_secrets = None
    if from_secrets:
        return str(from_secrets)

    from_env = os.getenv("DATABASE_URL")
    if from_env:
        return from_env

    return None


def _use_postgres() -> bool:
    return bool(_get_database_url()) and psycopg2 is not None


@st.cache_resource(show_spinner=False)
def _postgres_pool(database_url: str):
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed")

    return psycopg2.pool.ThreadedConnectionPool(
        1,
        5,
        dsn=database_url,
        connect_timeout=10,
        application_name="faglig_tinder",
    )


def _db_path() -> str:
    try:
        configured = st.secrets.get("sqlite_db_path")
    except Exception:
        configured = None
    if configured:
        return str(configured)
    return os.path.join(os.path.dirname(__file__), "faglig_tinder.db")


def _adapt_sql(sql: str) -> str:
    # App code uses sqlite-style '?' placeholders.
    return sql.replace("?", "%s") if _use_postgres() else sql


def _is_locked_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "database is locked" in msg or "database table is locked" in msg or "could not obtain lock" in msg


@contextmanager
def _connect():
    if _use_postgres():
        pool = _postgres_pool(_get_database_url())
        conn = pool.getconn()
        try:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            except Exception:
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    conn.close()
                conn = pool.getconn()
            yield conn
        finally:
            try:
                conn.rollback()
            except Exception:
                pass
            pool.putconn(conn)
        return

    conn = sqlite3.connect(_db_path(), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    if _use_postgres():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS Users (
                        id BIGSERIAL PRIMARY KEY,
                        navn TEXT NOT NULL UNIQUE
                    );

                    CREATE TABLE IF NOT EXISTS Problem (
                        id BIGSERIAL PRIMARY KEY,
                        tekst TEXT NOT NULL,
                        userId BIGINT NOT NULL REFERENCES Users(id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS Vote (
                        userId BIGINT NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
                        problemId BIGINT NOT NULL REFERENCES Problem(id) ON DELETE CASCADE,
                        PRIMARY KEY (userId, problemId)
                    );

                    CREATE INDEX IF NOT EXISTS idx_problem_user ON Problem(userId);
                    CREATE INDEX IF NOT EXISTS idx_vote_problem_user ON Vote(problemId, userId);
                    """
                )
            conn.commit()
        return

    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS Users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                navn TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS Problem (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tekst TEXT NOT NULL,
                userId INTEGER NOT NULL,
                FOREIGN KEY (userId) REFERENCES Users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS Vote (
                userId INTEGER NOT NULL,
                problemId INTEGER NOT NULL,
                PRIMARY KEY (userId, problemId),
                FOREIGN KEY (userId) REFERENCES Users(id) ON DELETE CASCADE,
                FOREIGN KEY (problemId) REFERENCES Problem(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_problem_user ON Problem(userId);
            CREATE INDEX IF NOT EXISTS idx_vote_problem_user ON Vote(problemId, userId);
            """
        )
        conn.commit()


def fetchone(sql: str, params=()):
    sql = _adapt_sql(sql)
    last_exc = None
    for attempt in range(5):
        try:
            with _connect() as conn:
                if _use_postgres():
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute(sql, params)
                        return cur.fetchone()
                cur = conn.execute(sql, params)
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as exc:
            last_exc = exc
            if _is_locked_error(exc) and attempt < 4:
                time.sleep(0.05 * (2 ** attempt))
                continue
            raise
    if last_exc:
        raise last_exc


def fetchall(sql: str, params=()):
    sql = _adapt_sql(sql)
    last_exc = None
    for attempt in range(5):
        try:
            with _connect() as conn:
                if _use_postgres():
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute(sql, params)
                        return cur.fetchall()
                cur = conn.execute(sql, params)
                rows = cur.fetchall()
                return [dict(r) for r in rows]
        except Exception as exc:
            last_exc = exc
            if _is_locked_error(exc) and attempt < 4:
                time.sleep(0.05 * (2 ** attempt))
                continue
            raise
    if last_exc:
        raise last_exc


def execute(sql: str, params=()):
    sql = _adapt_sql(sql)
    last_exc = None
    for attempt in range(6):
        try:
            with _connect() as conn:
                if _use_postgres():
                    with conn.cursor() as cur:
                        cur.execute(sql, params)
                        returned_id = None
                        if cur.description:
                            one = cur.fetchone()
                            if one:
                                returned_id = one[0]
                        conn.commit()
                        return returned_id

                cur = conn.execute(sql, params)
                returned_id = None
                if cur.description:
                    one = cur.fetchone()
                    if one:
                        returned_id = one[0]
                conn.commit()
                return returned_id if returned_id is not None else cur.lastrowid
        except Exception as exc:
            last_exc = exc
            if _is_locked_error(exc) and attempt < 5:
                time.sleep(0.08 * (2 ** attempt))
                continue
            raise
    if last_exc:
        raise last_exc
