"""
Urban Lex Tracker — Database Module
SQLite database for users, alerts, scrape history, and keywords.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ult_database.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Initialize all database tables."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            nombre TEXT DEFAULT '',
            profesion TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT DEFAULT '',
            url TEXT DEFAULT '',
            date TEXT DEFAULT '',
            category TEXT DEFAULT 'general',
            is_new INTEGER DEFAULT 1,
            html_report TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS scrape_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            items_found INTEGER DEFAULT 0,
            status TEXT DEFAULT 'success',
            error_message TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS user_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, keyword)
        );
    """)
    conn.commit()
    conn.close()


# ─── User Operations ───


def get_user_by_email(email: str):
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(user) if user else None


def get_user_by_id(user_id: int):
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None


def create_user(
    email: str, hashed_password: str, nombre: str = "", profesion: str = ""
):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (email, hashed_password, nombre, profesion) VALUES (?, ?, ?, ?)",
            (email, hashed_password, nombre, profesion),
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        return dict(user)
    except sqlite3.IntegrityError:
        conn.close()
        return None


def update_user(user_id: int, nombre: str = None, profesion: str = None):
    conn = get_connection()
    if nombre is not None:
        conn.execute("UPDATE users SET nombre = ? WHERE id = ?", (nombre, user_id))
    if profesion is not None:
        conn.execute(
            "UPDATE users SET profesion = ? WHERE id = ?", (profesion, user_id)
        )
    conn.commit()
    conn.close()


# ─── Alert Operations ───


def save_alert(
    source: str,
    title: str,
    summary: str = "",
    url: str = "",
    date: str = "",
    category: str = "general",
    html_report: str = "",
) -> bool:
    conn = get_connection()
    # Avoid exact duplicates
    existing = conn.execute(
        "SELECT id FROM alerts WHERE source = ? AND title = ?", (source, title)
    ).fetchone()
    if existing:
        conn.close()
        return False
    conn.execute(
        "INSERT INTO alerts (source, title, summary, url, date, category, html_report) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (source, title, summary, url, date, category, html_report),
    )
    conn.commit()
    conn.close()
    return True


def get_alerts(
    source: str = None,
    limit: int = 50,
    offset: int = 0,
    search: str = None,
    today_only: bool = False,
):
    conn = get_connection()
    query = "SELECT * FROM alerts"
    params = []
    conditions = []

    if source and source != "all":
        conditions.append("source = ?")
        params.append(source)
    if search:
        conditions.append("(title LIKE ? OR summary LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if today_only:
        conditions.append("date(created_at) = date('now')")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    alerts = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(a) for a in alerts]


def get_alert_count():
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) as c FROM alerts").fetchone()["c"]
    today = conn.execute(
        "SELECT COUNT(*) as c FROM alerts WHERE date(created_at) = date('now')"
    ).fetchone()["c"]
    new_count = conn.execute(
        "SELECT COUNT(*) as c FROM alerts WHERE is_new = 1"
    ).fetchone()["c"]
    conn.close()
    return {"total": total, "today": today, "new": new_count}


def mark_alerts_read():
    conn = get_connection()
    conn.execute("UPDATE alerts SET is_new = 0 WHERE is_new = 1")
    conn.commit()
    conn.close()


# ─── Scrape History ───


def save_scrape_history(
    source: str, items_found: int, status: str = "success", error_message: str = ""
):
    conn = get_connection()
    conn.execute(
        "INSERT INTO scrape_history (source, items_found, status, error_message) VALUES (?, ?, ?, ?)",
        (source, items_found, status, error_message),
    )
    conn.commit()
    conn.close()


def get_sources_status():
    conn = get_connection()
    sources_map = {
        "diario-oficial": "Diario Oficial",
        "contraloria": "Contraloría",
        "minvu": "MINVU",
        "bcn": "BCN",
        "poder-judicial": "Poder Judicial",
        "prensa": "Prensa",
        "proyectos-ley": "Proyectos de Ley",
        "ipt": "IPT",
        "sea": "SEA",
    }
    result = []
    for key, display_name in sources_map.items():
        # Get alerts ONLY for today for the "items_found_today" count
        # Usamos localtime para evitar el desfase UTC de SQLite y sumamos que coincida con "is_new" por seguridad de escaneo fresco
        today_count = conn.execute(
            "SELECT COUNT(*) as c FROM alerts WHERE source = ? AND (date(created_at, 'localtime') = date('now', 'localtime') OR date = ?)",
            (key, datetime.now().strftime("%Y-%m-%d")),
        ).fetchone()["c"]

        last = conn.execute(
            "SELECT * FROM scrape_history WHERE source = ? ORDER BY timestamp DESC LIMIT 1",
            (key,),
        ).fetchone()
        if last:
            result.append(
                {
                    "source": key,
                    "display_name": display_name,
                    "last_scrape": last["timestamp"],
                    "items_found": today_count,
                    "status": last["status"],
                }
            )
        else:
            result.append(
                {
                    "source": key,
                    "display_name": display_name,
                    "last_scrape": None,
                    "items_found": 0,
                    "status": "never",
                }
            )
    conn.close()
    return result


# ─── User Keywords ───


def get_user_keywords(user_id: int):
    conn = get_connection()
    keywords = conn.execute(
        "SELECT keyword FROM user_keywords WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return [k["keyword"] for k in keywords]


def add_user_keyword(user_id: int, keyword: str):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO user_keywords (user_id, keyword) VALUES (?, ?)",
            (user_id, keyword.strip().lower()),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def remove_user_keyword(user_id: int, keyword: str):
    conn = get_connection()
    conn.execute(
        "DELETE FROM user_keywords WHERE user_id = ? AND keyword = ?",
        (user_id, keyword.strip().lower()),
    )
    conn.commit()
    conn.close()
