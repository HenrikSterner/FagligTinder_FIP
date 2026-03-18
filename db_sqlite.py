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

try:
    import pymysql
    import pymysql.cursors
except Exception:
    pymysql = None


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


def _secret_or_env(*names: str) -> str | None:
    for name in names:
        try:
            value = st.secrets.get(name)
        except Exception:
            value = None
        if value not in (None, ""):
            return str(value)

        value = os.getenv(name)
        if value not in (None, ""):
            return str(value)
    return None


def _get_mysql_config() -> dict | None:
    host = _secret_or_env("DB_ADDRESS", "db_address", "MYSQL_HOST", "mysql_host")
    user = _secret_or_env("DB_USER", "db_user", "MYSQL_USER", "mysql_user")
    password = _secret_or_env("DB_PASS", "db_pass", "MYSQL_PASSWORD", "mysql_password")
    database = _secret_or_env("DB_NAME", "db_name", "MYSQL_DATABASE", "mysql_database")
    port_raw = _secret_or_env("DB_PORT", "db_port", "MYSQL_PORT", "mysql_port")

    if not (host and user and password and database):
        return None

    port = int(port_raw) if port_raw else 3306
    return {
        "host": host,
        "user": user,
        "password": password,
        "database": database,
        "port": port,
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor if pymysql else None,
        "autocommit": False,
        "connect_timeout": 10,
    }


def _use_postgres() -> bool:
    return bool(_get_database_url()) and psycopg2 is not None


def _use_mysql() -> bool:
    return _get_mysql_config() is not None and pymysql is not None


def is_postgres() -> bool:
    return _use_postgres()


def is_mysql() -> bool:
    return _use_mysql()


def _mysql_ensure_index(cur, table_name: str, index_name: str, ddl: str) -> None:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND index_name = %s
        LIMIT 1
        """,
        (table_name, index_name),
    )
    if not cur.fetchone():
        cur.execute(ddl)


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
    adapted = sql.replace("?", "%s") if (_use_postgres() or _use_mysql()) else sql
    if _use_mysql():
        adapted = adapted.replace(" RETURNING id", "")
    return adapted


def _is_locked_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "database is locked" in msg
        or "database table is locked" in msg
        or "could not obtain lock" in msg
        or "lock wait timeout exceeded" in msg
        or "deadlock found" in msg
    )


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

    if _use_mysql():
        conn = pymysql.connect(**_get_mysql_config())
        try:
            yield conn
        finally:
            conn.close()
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

    if _use_mysql():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS Users (
                        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        navn VARCHAR(255) NOT NULL UNIQUE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS Problem (
                        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        tekst TEXT NOT NULL,
                        userId BIGINT NOT NULL,
                        CONSTRAINT fk_problem_user
                            FOREIGN KEY (userId) REFERENCES Users(id)
                            ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS Vote (
                        userId BIGINT NOT NULL,
                        problemId BIGINT NOT NULL,
                        PRIMARY KEY (userId, problemId),
                        CONSTRAINT fk_vote_user
                            FOREIGN KEY (userId) REFERENCES Users(id)
                            ON DELETE CASCADE,
                        CONSTRAINT fk_vote_problem
                            FOREIGN KEY (problemId) REFERENCES Problem(id)
                            ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                _mysql_ensure_index(
                    cur,
                    "Problem",
                    "idx_problem_user",
                    "CREATE INDEX idx_problem_user ON Problem(userId)",
                )
                _mysql_ensure_index(
                    cur,
                    "Vote",
                    "idx_vote_problem_user",
                    "CREATE INDEX idx_vote_problem_user ON Vote(problemId, userId)",
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
                if _use_mysql():
                    with conn.cursor() as cur:
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
                if _use_mysql():
                    with conn.cursor() as cur:
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

                if _use_mysql():
                    with conn.cursor() as cur:
                        cur.execute(sql, params)
                        returned_id = None
                        if cur.description:
                            one = cur.fetchone()
                            if one:
                                returned_id = next(iter(one.values()))
                        conn.commit()
                        return returned_id if returned_id is not None else cur.lastrowid

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
