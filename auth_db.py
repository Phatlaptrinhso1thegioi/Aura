#!/usr/bin/env python3
"""SQLite Database and Authentication Manager for AURA."""

import datetime
import hashlib
import json
import os
import secrets
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aura.db")


def get_connection(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path=None):
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                full_name TEXT NOT NULL,
                avatar TEXT DEFAULT 'aura-cat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_data (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                likes_json TEXT NOT NULL DEFAULT '[]',
                playlists_json TEXT NOT NULL DEFAULT '[]',
                saved_playlists_json TEXT NOT NULL DEFAULT '["p-dreamy", "p-focus"]',
                recent_json TEXT NOT NULL DEFAULT '[]',
                prefs_json TEXT NOT NULL DEFAULT '{}',
                custom_tracks_json TEXT NOT NULL DEFAULT '[]',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            """
        )


def hash_password(password: str, salt: str = None):
    if salt is None:
        salt = secrets.token_hex(16)
    pwd_bytes = password.encode("utf-8")
    salt_bytes = salt.encode("utf-8")
    hash_bytes = hashlib.pbkdf2_hmac("sha256", pwd_bytes, salt_bytes, 100000)
    return hash_bytes.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    calc_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(calc_hash, stored_hash)


def register_user(email: str, password: str, full_name: str, db_path=None):
    clean_email = (email or "").strip().lower()
    clean_name = (full_name or "").strip()
    if not clean_email or "@" not in clean_email:
        raise ValueError("Email không hợp lệ.")
    if not password or len(password) < 6:
        raise ValueError("Mật khẩu phải có ít nhất 6 ký tự.")
    if not clean_name:
        clean_name = clean_email.split("@")[0].capitalize()

    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (clean_email,))
        if cursor.fetchone():
            raise ValueError("Email này đã được đăng ký. Vui lòng đăng nhập.")

        user_id = "u_" + secrets.token_hex(8)
        pwd_hash, salt = hash_password(password)

        cursor.execute(
            """
            INSERT INTO users (id, email, password_hash, salt, full_name, avatar)
            VALUES (?, ?, ?, ?, ?, 'aura-cat')
            """,
            (user_id, clean_email, pwd_hash, salt, clean_name),
        )

        initial_prefs = {
            "username": clean_name,
            "theme": "light",
            "autoNext": True,
            "reduceMotion": False,
            "favGenres": ["V-Pop", "Indie Việt"],
        }

        cursor.execute(
            """
            INSERT INTO user_data (user_id, likes_json, playlists_json, saved_playlists_json, recent_json, prefs_json, custom_tracks_json)
            VALUES (?, '["t1", "t2"]', '[]', '["p-dreamy", "p-focus"]', '["t1"]', ?, '[]')
            """,
            (user_id, json.dumps(initial_prefs, ensure_ascii=False)),
        )

        token = secrets.token_hex(32)
        cursor.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
        conn.commit()

        user_dict = {
            "id": user_id,
            "email": clean_email,
            "full_name": clean_name,
            "avatar": "aura-cat",
        }
        data_dict = {
            "likes": ["t1", "t2"],
            "playlists": [],
            "savedPlaylists": ["p-dreamy", "p-focus"],
            "recent": ["t1"],
            "prefs": initial_prefs,
            "customTracks": [],
        }
        return user_dict, token, data_dict


def login_user(email: str, password: str, db_path=None):
    clean_email = (email or "").strip().lower()
    if not clean_email or not password:
        raise ValueError("Vui lòng nhập đầy đủ Email và Mật khẩu.")

    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, email, password_hash, salt, full_name, avatar
            FROM users WHERE email = ?
            """,
            (clean_email,),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Email hoặc mật khẩu không chính xác.")

        if not verify_password(password, row["password_hash"], row["salt"]):
            raise ValueError("Email hoặc mật khẩu không chính xác.")

        user_id = row["id"]
        token = secrets.token_hex(32)
        cursor.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))

        cursor.execute("SELECT * FROM user_data WHERE user_id = ?", (user_id,))
        data_row = cursor.fetchone()
        conn.commit()

        user_dict = {
            "id": user_id,
            "email": row["email"],
            "full_name": row["full_name"],
            "avatar": row["avatar"] or "aura-cat",
        }

        if data_row:
            data_dict = {
                "likes": json.loads(data_row["likes_json"] or "[]"),
                "playlists": json.loads(data_row["playlists_json"] or "[]"),
                "savedPlaylists": json.loads(data_row["saved_playlists_json"] or '["p-dreamy", "p-focus"]'),
                "recent": json.loads(data_row["recent_json"] or "[]"),
                "prefs": json.loads(data_row["prefs_json"] or "{}"),
                "customTracks": json.loads(data_row["custom_tracks_json"] or "[]"),
            }
        else:
            data_dict = {
                "likes": [],
                "playlists": [],
                "savedPlaylists": ["p-dreamy", "p-focus"],
                "recent": [],
                "prefs": {"username": row["full_name"]},
                "customTracks": [],
            }

        return user_dict, token, data_dict


def get_user_by_token(token: str, db_path=None):
    if not token:
        return None, None

    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT u.id, u.email, u.full_name, u.avatar,
                   d.likes_json, d.playlists_json, d.saved_playlists_json,
                   d.recent_json, d.prefs_json, d.custom_tracks_json
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            LEFT JOIN user_data d ON u.id = d.user_id
            WHERE s.token = ?
            """,
            (token,),
        )
        row = cursor.fetchone()
        if not row:
            return None, None

        user_dict = {
            "id": row["id"],
            "email": row["email"],
            "full_name": row["full_name"],
            "avatar": row["avatar"] or "aura-cat",
        }
        data_dict = {
            "likes": json.loads(row["likes_json"] or "[]"),
            "playlists": json.loads(row["playlists_json"] or "[]"),
            "savedPlaylists": json.loads(row["saved_playlists_json"] or '["p-dreamy", "p-focus"]'),
            "recent": json.loads(row["recent_json"] or "[]"),
            "prefs": json.loads(row["prefs_json"] or "{}"),
            "customTracks": json.loads(row["custom_tracks_json"] or "[]"),
        }
        return user_dict, data_dict


def logout_user(token: str, db_path=None):
    if not token:
        return
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def save_user_data(user_id: str, data_dict: dict, db_path=None):
    if not user_id:
        return
    init_db(db_path)
    with get_connection(db_path) as conn:
        likes_j = json.dumps(data_dict.get("likes", []), ensure_ascii=False)
        playlists_j = json.dumps(data_dict.get("playlists", []), ensure_ascii=False)
        saved_j = json.dumps(data_dict.get("savedPlaylists", ["p-dreamy", "p-focus"]), ensure_ascii=False)
        recent_j = json.dumps(data_dict.get("recent", []), ensure_ascii=False)
        prefs_j = json.dumps(data_dict.get("prefs", {}), ensure_ascii=False)
        custom_j = json.dumps(data_dict.get("customTracks", []), ensure_ascii=False)
        now = datetime.datetime.utcnow().isoformat()

        conn.execute(
            """
            INSERT INTO user_data (user_id, likes_json, playlists_json, saved_playlists_json, recent_json, prefs_json, custom_tracks_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                likes_json = excluded.likes_json,
                playlists_json = excluded.playlists_json,
                saved_playlists_json = excluded.saved_playlists_json,
                recent_json = excluded.recent_json,
                prefs_json = excluded.prefs_json,
                custom_tracks_json = excluded.custom_tracks_json,
                updated_at = excluded.updated_at
            """,
            (user_id, likes_j, playlists_j, saved_j, recent_j, prefs_j, custom_j, now),
        )
        conn.commit()
