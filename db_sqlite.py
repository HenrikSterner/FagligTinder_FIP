import os
import sqlite3
import time

import streamlit as st


def _db_path() -> str:
    # Optional override via secrets, fallback to local db file next to app files.
    configured = None
    try:
        configured = st.secrets.get("sqlite_db_path")
    except Exception:
        configured = None
    if configured:
        return str(configured)
    return os.path.join(os.path.dirname(__file__), "faglig_tinder.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _is_locked_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "database is locked" in msg or "database table is locked" in msg


def init_db() -> None:
    conn = _connect()
    try:
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
            """
        )
        conn.commit()
    finally:
        conn.close()


def fetchone(sql: str, params=()):
    last_exc = None
    for attempt in range(5):
        conn = _connect()
        try:
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if _is_locked_error(exc) and attempt < 4:
                time.sleep(0.05 * (2 ** attempt))
                continue
            raise
        finally:
            conn.close()
    if last_exc:
        raise last_exc


def fetchall(sql: str, params=()):
    last_exc = None
    for attempt in range(5):
        conn = _connect()
        try:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if _is_locked_error(exc) and attempt < 4:
                time.sleep(0.05 * (2 ** attempt))
                continue
            raise
        finally:
            conn.close()
    if last_exc:
        raise last_exc


def execute(sql: str, params=()):
    last_exc = None
    for attempt in range(6):
        conn = _connect()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.lastrowid
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if _is_locked_error(exc) and attempt < 5:
                time.sleep(0.08 * (2 ** attempt))
                continue
            raise
        finally:
            conn.close()
    if last_exc:
        raise last_exc
