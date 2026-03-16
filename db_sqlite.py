import os
import sqlite3

import streamlit as st


def _db_path() -> str:
    # Optional override via secrets, fallback to local db file next to app files.
    configured = st.secrets.get("sqlite_db_path")
    if configured:
        return str(configured)
    return os.path.join(os.path.dirname(__file__), "faglig_tinder.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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
    conn = _connect()
    try:
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def fetchall(sql: str, params=()):
    conn = _connect()
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def execute(sql: str, params=()):
    conn = _connect()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()
