import os


def load_env_file(path="data.env"):
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and not os.environ.get(key):
                os.environ[key] = value


load_env_file()

EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")


from flask import Flask, render_template, redirect, url_for, request, jsonify, session
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from rag_engine import get_rag_response
    RAG_IMPORT_ERROR = None
except ImportError as e:
    get_rag_response = None
    RAG_IMPORT_ERROR = e



def send_otp_email(receiver_email, otp):
    sender_email = EMAIL_ADDRESS
    sender_password = EMAIL_PASSWORD

    if not sender_email or not sender_password:
        print("Email error: EMAIL_ADDRESS or EMAIL_PASSWORD is not configured")
        return False

    subject = "Your OTP for Legal E-Learning"
    body = f"""
Hello,

Your OTP for Legal E-Learning is:

{otp}

This OTP will expire in 5 minutes.

If you did not request this, please ignore.

Regards,
Legal E-Learning Team
"""

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print("Email error:", e)
        return False

def generate_otp():
    return str(random.randint(100000, 999999))


def get_db_connection():
    Path("database").mkdir(exist_ok=True)
    conn = sqlite3.connect("database/app.db")
    conn.row_factory = sqlite3.Row
    return conn

def ensure_chat_schema():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_verified INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS otp_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            otp_code TEXT NOT NULL,
            is_verified INTEGER DEFAULT 0,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
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
    conn.execute("""
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

    columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(chats)").fetchall()
    ]
    if "thread_id" not in columns:
        conn.execute("ALTER TABLE chats ADD COLUMN thread_id INTEGER")

    otp_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(otp_requests)").fetchall()
    ]
    if "is_verified" not in otp_columns:
        conn.execute("ALTER TABLE otp_requests ADD COLUMN is_verified INTEGER DEFAULT 0")

    orphan_chats = conn.execute("""
        SELECT id, user_id, issue, message, created_at
        FROM chats
        WHERE thread_id IS NULL
        ORDER BY id
    """).fetchall()

    for chat in orphan_chats:
        title = make_thread_title(chat["message"])
        cursor = conn.execute("""
            INSERT INTO chat_threads (user_id, issue, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            chat["user_id"],
            chat["issue"],
            title,
            chat["created_at"],
            chat["created_at"]
        ))
        conn.execute("""
            UPDATE chats
            SET thread_id = ?
            WHERE id = ?
        """, (cursor.lastrowid, chat["id"]))

    conn.commit()
    conn.close()

def require_login():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return None


def generate_chat_response(issue, message):
    if get_rag_response is None:
        print("RAG import error:", RAG_IMPORT_ERROR)
        return (
            "The legal assistant is not available right now because the RAG "
            "engine could not be loaded. Please check the server logs."
        )

    try:
        return get_rag_response(issue, message)
    except Exception as e:
        print("RAG error:", e)
        return (
            f"I'm sorry, I encountered an error while processing your "
            f"{format_issue_name(issue)} query. Please try again."
        )

def format_issue_name(issue):
    issue_map = {
        "family-law": "Family Law",
        "property-disputes": "Property Disputes",
        "employment": "Employment Issues",
        "consumer-rights": "Consumer Rights",
        "criminal-law": "Criminal Law",
        "business-law": "Business Law",
        "civil-rights": "Civil Rights",
        "others": "General Legal"
    }
    return issue_map.get(issue, "General Legal")

def make_thread_title(message):
    title = (message or "Legal chat").strip()
    if len(title) > 70:
        return title[:67].rstrip() + "..."
    return title or "Legal chat"

def request_json():
    return request.get_json(silent=True) or {}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-to-a-random-secret-key")
ensure_chat_schema()


@app.route("/")
def login():
    return render_template("login.html")


@app.route("/ask", methods=["POST"])
def ask():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request_json()
    issue = data.get("issue", "others")
    message = data.get("message", "").strip()
    thread_id = data.get("thread_id")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    conn = get_db_connection()

    if thread_id:
        thread = conn.execute("""
            SELECT id, issue
            FROM chat_threads
            WHERE id = ? AND user_id = ?
        """, (thread_id, session["user_id"])).fetchone()

        if thread is None:
            conn.close()
            return jsonify({"error": "Thread not found"}), 404

        issue = thread["issue"] or issue
    else:
        cursor = conn.execute("""
            INSERT INTO chat_threads (user_id, issue, title)
            VALUES (?, ?, ?)
        """, (session["user_id"], issue, make_thread_title(message)))
        thread_id = cursor.lastrowid

    response_text = generate_chat_response(issue, message)

    conn.execute("""
        INSERT INTO chats (thread_id, user_id, issue, message, response)
        VALUES (?, ?, ?, ?, ?)
    """, (thread_id, session["user_id"], issue, message, response_text))
    conn.execute("""
        UPDATE chat_threads
        SET updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, (thread_id, session["user_id"]))
    conn.commit()
    conn.close()

    return jsonify({
        "reply": response_text,
        "thread_id": thread_id
    })

@app.route("/login", methods=["POST"])
def do_login():
    data = request_json()
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        (email,)
    ).fetchone()
    conn.close()

    if user is None:
        return jsonify({"error": "Invalid email or password"}), 401

    if not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]

    return jsonify({
        "message": "Login successful",
        "redirect": url_for("home")
    })



@app.route("/signup")
def signup():
    return render_template("signup.html")

@app.route("/home")
def home():
    auth = require_login()
    if auth:
        return auth
    return render_template("home.html")

@app.route("/history")
def history():
    auth = require_login()
    if auth:
        return auth

    conn = get_db_connection()
    rows = conn.execute("""
        SELECT
            t.id,
            t.issue,
            t.title,
            t.created_at,
            t.updated_at,
            COUNT(c.id) AS message_count
        FROM chat_threads t
        LEFT JOIN chats c ON c.thread_id = t.id
        WHERE t.user_id = ?
        GROUP BY t.id
        ORDER BY t.updated_at DESC, t.id DESC
    """, (session["user_id"],)).fetchall()
    conn.close()

    threads = []
    for row in rows:
        threads.append({
            "id": row["id"],
            "issue": row["issue"],
            "issue_label": format_issue_name(row["issue"]),
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "message_count": row["message_count"]
        })

    return render_template("history.html", threads=threads)

@app.route("/profile")
def profile():
    auth = require_login()
    if auth:
        return auth

    conn = get_db_connection()
    user = conn.execute("""
        SELECT id, name, email
        FROM users
        WHERE id = ?
    """, (session["user_id"],)).fetchone()
    conn.close()

    return render_template("profile.html", user=user)



@app.route("/profile/update", methods=["POST"])
def update_profile():
    auth = require_login()
    if auth:
        return jsonify({"error": "Unauthorized"}), 401

    data = request_json()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not name or not email:
        return jsonify({"error": "Name and email are required"}), 400
    if password and len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters long"}), 400

    conn = get_db_connection()

    existing_user = conn.execute("""
        SELECT id FROM users
        WHERE email = ? AND id != ?
    """, (email, session["user_id"])).fetchone()

    if existing_user:
        conn.close()
        return jsonify({"error": "Email is already in use"}), 400

    if password:
        password_hash = generate_password_hash(password)
        conn.execute("""
            UPDATE users
            SET name = ?, email = ?, password_hash = ?
            WHERE id = ?
        """, (name, email, password_hash, session["user_id"]))
    else:
        conn.execute("""
            UPDATE users
            SET name = ?, email = ?
            WHERE id = ?
        """, (name, email, session["user_id"]))

    conn.commit()
    conn.close()

    session["user_name"] = name
    session["user_email"] = email

    return jsonify({"message": "Profile updated successfully"})



@app.route("/history/delete/<int:thread_id>", methods=["POST"])
def delete_history_item(thread_id):
    auth = require_login()
    if auth:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db_connection()
    conn.execute("""
        DELETE FROM chats
        WHERE thread_id = ? AND user_id = ?
    """, (thread_id, session["user_id"]))
    conn.execute("""
        DELETE FROM chat_threads
        WHERE id = ? AND user_id = ?
    """, (thread_id, session["user_id"]))
    conn.commit()
    conn.close()

    return jsonify({"message": "Thread deleted successfully"})


@app.route("/history/clear", methods=["POST"])
def clear_history():
    auth = require_login()
    if auth:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db_connection()
    conn.execute("""
        DELETE FROM chats
        WHERE user_id = ?
    """, (session["user_id"],))
    conn.execute("""
        DELETE FROM chat_threads
        WHERE user_id = ?
    """, (session["user_id"],))
    conn.commit()
    conn.close()

    return jsonify({"message": "History cleared successfully"})


@app.route("/chat/thread/<int:thread_id>")
def get_chat_thread(thread_id):
    auth = require_login()
    if auth:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db_connection()
    thread = conn.execute("""
        SELECT id, issue, title, created_at, updated_at
        FROM chat_threads
        WHERE id = ? AND user_id = ?
    """, (thread_id, session["user_id"])).fetchone()

    if thread is None:
        conn.close()
        return jsonify({"error": "Thread not found"}), 404

    rows = conn.execute("""
        SELECT id, message, response, created_at
        FROM chats
        WHERE thread_id = ? AND user_id = ?
        ORDER BY id ASC
    """, (thread_id, session["user_id"])).fetchall()
    conn.close()

    return jsonify({
        "thread": {
            "id": thread["id"],
            "issue": thread["issue"],
            "issue_label": format_issue_name(thread["issue"]),
            "title": thread["title"],
            "created_at": thread["created_at"],
            "updated_at": thread["updated_at"]
        },
        "messages": [
            {
                "id": row["id"],
                "message": row["message"],
                "response": row["response"],
                "created_at": row["created_at"]
            }
            for row in rows
        ]
    })


@app.route("/chatbot")
def chatbot():
    auth = require_login()
    if auth:
        return auth
    return render_template("chatbot.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/send-otp", methods=["POST"])
def send_otp():
    data = request_json()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()

    if not name or not email:
        return jsonify({"error": "Missing name or email"}), 400

    conn = get_db_connection()
    existing_user = conn.execute(
        "SELECT id FROM users WHERE email = ?",
        (email,)
    ).fetchone()
    if existing_user:
        conn.close()
        return jsonify({"error": "An account with this email already exists"}), 400

    otp = generate_otp()
    expires_at = datetime.now() + timedelta(minutes=5)

    cursor = conn.cursor()

    cursor.execute("DELETE FROM otp_requests WHERE email = ?", (email,))
    cursor.execute("""
        INSERT INTO otp_requests (name, email, otp_code, is_verified, expires_at)
        VALUES (?, ?, ?, 0, ?)
    """, (name, email, otp, expires_at))

    conn.commit()
    conn.close()

    email_sent = send_otp_email(email, otp)

    if not email_sent:
        return jsonify({"error": "Failed to send OTP email"}), 500

    return jsonify({"message": "OTP sent successfully"})


@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request_json()
    email = data.get("email", "").strip()
    otp = data.get("otp", "").strip()

    if not email or not otp:
        return jsonify({"error": "Email and OTP are required"}), 400

    conn = get_db_connection()
    record = conn.execute(
        "SELECT * FROM otp_requests WHERE email = ?",
        (email,)
    ).fetchone()

    conn.close()

    if not record:
        return jsonify({"error": "No OTP found"}), 400

    if record["otp_code"] != otp:
        return jsonify({"error": "Invalid OTP"}), 400

    if datetime.now() > datetime.fromisoformat(record["expires_at"]):
        conn = get_db_connection()
        conn.execute("DELETE FROM otp_requests WHERE email = ?", (email,))
        conn.commit()
        conn.close()
        return jsonify({"error": "OTP expired"}), 400

    conn = get_db_connection()
    conn.execute("""
        UPDATE otp_requests
        SET is_verified = 1
        WHERE email = ?
    """, (email,))
    conn.commit()
    conn.close()

    return jsonify({"message": "OTP verified"})

@app.route("/complete-signup", methods=["POST"])
def complete_signup():
    data = request_json()
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters long"}), 400

    conn = get_db_connection()

    record = conn.execute(
        "SELECT * FROM otp_requests WHERE email = ? AND is_verified = 1",
        (email,)
    ).fetchone()

    if not record:
        conn.close()
        return jsonify({"error": "OTP not verified"}), 400

    if datetime.now() > datetime.fromisoformat(record["expires_at"]):
        conn.execute("DELETE FROM otp_requests WHERE email = ?", (email,))
        conn.commit()
        conn.close()
        return jsonify({"error": "OTP expired"}), 400

    password_hash = generate_password_hash(password)

    try:
        conn.execute("""
            INSERT INTO users (name, email, password_hash, is_verified)
            VALUES (?, ?, ?, 1)
        """, (record["name"], email, password_hash))

        # delete OTP after use
        conn.execute("DELETE FROM otp_requests WHERE email = ?", (email,))
        conn.commit()

    except Exception as e:
        conn.close()
        return jsonify({"error": "User already exists"}), 400

    conn.close()
    return jsonify({"message": "Signup successful"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(host="0.0.0.0", port=port, debug=debug)
