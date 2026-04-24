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

    subject = "Your OTP for Legal E-Learner"
    body = f"""
Hello,

Your OTP for Legal E-Learner is:

{otp}

This OTP will expire in 5 minutes.

If you did not request this, please ignore.

Regards,
Legal E-Learner Team
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
    conn = sqlite3.connect("database/app.db")
    conn.row_factory = sqlite3.Row
    return conn

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

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-to-a-random-secret-key")


@app.route("/")
def login():
    return render_template("login.html")


@app.route("/ask", methods=["POST"])
def ask():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    issue = data.get("issue", "others")
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"error": "Message is required"}), 400

    response_text = generate_chat_response(issue, message)

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO chats (user_id, issue, message, response)
        VALUES (?, ?, ?, ?)
    """, (session["user_id"], issue, message, response_text))
    conn.commit()
    conn.close()

    return jsonify({
        "reply": response_text
    })

@app.route("/login", methods=["POST"])
def do_login():
    data = request.get_json()
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
        SELECT id, issue, message, response, created_at
        FROM chats
        WHERE user_id = ?
        ORDER BY id DESC
    """, (session["user_id"],)).fetchall()
    conn.close()

    chats = []
    for row in rows:
        chats.append({
            "id": row["id"],
            "issue": row["issue"],
            "issue_label": format_issue_name(row["issue"]),
            "message": row["message"],
            "response": row["response"],
            "created_at": row["created_at"]
        })

    return render_template("history.html", chats=chats)

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

    data = request.get_json()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not name or not email:
        return jsonify({"error": "Name and email are required"}), 400

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



@app.route("/history/delete/<int:chat_id>", methods=["POST"])
def delete_history_item(chat_id):
    auth = require_login()
    if auth:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db_connection()
    conn.execute("""
        DELETE FROM chats
        WHERE id = ? AND user_id = ?
    """, (chat_id, session["user_id"]))
    conn.commit()
    conn.close()

    return jsonify({"message": "Chat deleted successfully"})


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
    conn.commit()
    conn.close()

    return jsonify({"message": "History cleared successfully"})


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
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")

    if not name or not email:
        return jsonify({"error": "Missing name or email"}), 400

    otp = generate_otp()
    expires_at = datetime.now() + timedelta(minutes=5)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM otp_requests WHERE email = ?", (email,))
    cursor.execute("""
        INSERT INTO otp_requests (name, email, otp_code, expires_at)
        VALUES (?, ?, ?, ?)
    """, (name, email, otp, expires_at))

    conn.commit()
    conn.close()

    email_sent = send_otp_email(email, otp)

    if not email_sent:
        return jsonify({"error": "Failed to send OTP email"}), 500

    return jsonify({"message": "OTP sent successfully"})


@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json()
    email = data.get("email")
    otp = data.get("otp")

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
        return jsonify({"error": "OTP expired"}), 400

    return jsonify({"message": "OTP verified"})

@app.route("/complete-signup", methods=["POST"])
def complete_signup():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    conn = get_db_connection()

    record = conn.execute(
        "SELECT * FROM otp_requests WHERE email = ?",
        (email,)
    ).fetchone()

    if not record:
        conn.close()
        return jsonify({"error": "OTP not verified"}), 400

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
    app.run(host="0.0.0.0", port=5000, debug=True)
