import sqlite3
from pathlib import Path

Path("database").mkdir(exist_ok=True)
conn = sqlite3.connect("database/app.db")
cursor = conn.cursor()

# USERS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_verified INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# OTP TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS otp_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    otp_code TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# CHAT TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS chat_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    issue TEXT,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER,
    user_id INTEGER NOT NULL,
    issue TEXT,
    message TEXT,
    response TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(thread_id) REFERENCES chat_threads(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

columns = [row[1] for row in cursor.execute("PRAGMA table_info(chats)").fetchall()]
if "thread_id" not in columns:
    cursor.execute("ALTER TABLE chats ADD COLUMN thread_id INTEGER")

orphan_chats = cursor.execute("""
    SELECT id, user_id, issue, message, created_at
    FROM chats
    WHERE thread_id IS NULL
    ORDER BY id
""").fetchall()

for chat_id, user_id, issue, message, created_at in orphan_chats:
    title = (message or "Legal chat").strip()
    if len(title) > 70:
        title = title[:67].rstrip() + "..."

    cursor.execute("""
        INSERT INTO chat_threads (user_id, issue, title, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, issue, title, created_at, created_at))

    cursor.execute("""
        UPDATE chats
        SET thread_id = ?
        WHERE id = ?
    """, (cursor.lastrowid, chat_id))

conn.commit()
conn.close()

print("Database initialized successfully.")
