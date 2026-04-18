import sqlite3
import hashlib
import secrets
import os
import re
from datetime import datetime


DB_PATH = os.getenv("DB_PATH", "reportly.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         TEXT PRIMARY KEY,
            email      TEXT UNIQUE NOT NULL,
            password   TEXT NOT NULL,
            salt       TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            data       TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode()).hexdigest()


def validate_email(email: str) -> bool:
    return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", email))


def validate_password(password: str) -> tuple:
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number."
    return True, "OK"


def create_user(email: str, password: str) -> tuple:
    if not validate_email(email):
        return False, "Invalid email address."

    valid, msg = validate_password(password)
    if not valid:
        return False, msg

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email.lower(),)
        ).fetchone()

        if existing:
            return False, "An account with this email already exists."

        salt       = secrets.token_hex(32)
        hashed     = hash_password(password, salt)
        user_id    = secrets.token_hex(16)
        created_at = datetime.utcnow().isoformat()

        conn.execute(
            "INSERT INTO users (id, email, password, salt, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email.lower(), hashed, salt, created_at)
        )
        conn.commit()
        return True, "Account created successfully."

    except Exception as e:
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> tuple:
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower(),)
        ).fetchone()

        if not user:
            return False, None

        hashed = hash_password(password, user["salt"])
        if hashed != user["password"]:
            return False, None

        return True, dict(user)

    except Exception as e:
        return False, None
    finally:
        conn.close()


def get_user_by_id(user_id: str) -> dict:
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(user) if user else None
    finally:
        conn.close()


def save_report_to_db(user_id: str, report_data: dict) -> bool:
    conn = get_db()
    try:
        import json
        report_id  = secrets.token_hex(16)
        created_at = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO reports (id, user_id, data, created_at) VALUES (?, ?, ?, ?)",
            (report_id, user_id, json.dumps(report_data), created_at)
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_reports_from_db(user_id: str, limit: int = 6) -> list:
    conn = get_db()
    try:
        import json
        rows = conn.execute(
            "SELECT data, created_at FROM reports WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        reports = []
        for row in rows:
            try:
                data = json.loads(row["data"])
                data["_saved_at"] = row["created_at"]
                reports.append(data)
            except Exception:
                continue
        return reports
    finally:
        conn.close()