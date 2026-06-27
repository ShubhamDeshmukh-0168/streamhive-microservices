import os
import random
import re
import threading
from html import escape
from datetime import datetime, timedelta

import pymysql
from flask import Flask, jsonify, request
from flask_mail import Mail, Message
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


@app.before_request
def handle_cors_preflight():
    if request.method == "OPTIONS":
        return "", 204


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


db_config = {
    "host": os.getenv("DB_HOST", ""),
    "user": os.getenv("DB_USER", ""),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "streamhive"),
}

app.config.update(
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", "587")),
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
    MAIL_DEFAULT_SENDER=os.getenv("MAIL_USERNAME", ""),
)

mail = Mail(app)


def get_db_connection():
    return pymysql.connect(
        host=db_config["host"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def get_json_payload():
    return request.get_json(silent=True) or {}


def require_fields(data, fields):
    missing = [f for f in fields if not str(data.get(f, "")).strip()]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
    return None


def validate_password_strength(password):
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", password):
        return "Password must include at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return "Password must include at least one lowercase letter."
    if not re.search(r"\d", password):
        return "Password must include at least one number."
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must include at least one special character."
    return None


def fetch_user_by_email(cursor, email):
    cursor.execute(
        """
        SELECT id, username, full_name, email, address, phone, otp_code, otp_expiry,
               last_login_otp_verified_at
        FROM users WHERE email = %s
        """,
        (email,),
    )
    return cursor.fetchone()


def should_require_daily_login_otp(user):
    last_verified = user.get("last_login_otp_verified_at")
    if not last_verified:
        return True
    return last_verified.date() != datetime.now().date()


def serialize_watchlist_row(row):
    return {
        "id": row["id"],
        "item_id": row["item_id"],
        "item_title": row["item_title"],
        "item_thumbnail": row["item_thumbnail"],
        "category": row["category"],
        "price": float(row["price"]),
        "quantity": row["quantity"],
        "subtotal": float(row["price"]) * row["quantity"],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def fetch_watchlist(cursor, user_id):
    cursor.execute(
        """
        SELECT id, item_id, item_title, item_thumbnail, category, price, quantity, updated_at
        FROM watchlist_items WHERE user_id = %s
        ORDER BY updated_at DESC, id DESC
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    items = [serialize_watchlist_row(r) for r in rows]
    total = round(sum(i["subtotal"] for i in items), 2)
    return {"items": items, "total": total}


def ensure_booking_tables(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            customer_name VARCHAR(150) NOT NULL,
            customer_email VARCHAR(150) NOT NULL,
            delivery_address TEXT DEFAULT NULL,
            customer_phone VARCHAR(20) DEFAULT NULL,
            total_amount DECIMAL(10, 2) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'confirmed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CONSTRAINT fk_bookings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS booking_items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            booking_id INT NOT NULL,
            item_id VARCHAR(100) NOT NULL,
            item_title VARCHAR(255) NOT NULL,
            item_thumbnail TEXT DEFAULT NULL,
            price DECIMAL(10, 2) NOT NULL,
            quantity INT NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_booking_items_booking FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
        )
        """
    )


def ensure_activity_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            app_name VARCHAR(100) NOT NULL,
            app_path VARCHAR(255) DEFAULT NULL,
            activity_type VARCHAR(50) NOT NULL DEFAULT 'open',
            note VARCHAR(255) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_activity_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )


def build_booking_receipt(payload):
    items = payload.get("items") or []
    item_lines = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #2a2a3d;'>{escape(str(i.get('item_title')))}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #2a2a3d;text-align:center;'>{int(i.get('quantity') or 0)}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #2a2a3d;text-align:right;'>Rs. {float(i.get('price') or 0):.2f}</td></tr>"
        for i in items
    ) or "<tr><td colspan='3'>No items found.</td></tr>"

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:680px;margin:0 auto;padding:24px;background:#0f0f1a;color:#f1f1f1;">
      <h2 style="color:#a855f7;">StreamHive Booking Confirmed 🎬</h2>
      <p>Hi {escape(str(payload['customer_name']))}, your booking <strong>#{payload['id']}</strong> is confirmed.</p>
      <table style="width:100%;border-collapse:collapse;margin:16px 0;">
        <thead><tr style="background:#1c1c2e;"><th style="padding:8px;text-align:left;">Item</th><th>Qty</th><th>Price</th></tr></thead>
        <tbody>{item_lines}</tbody>
      </table>
      <p><strong>Total Paid:</strong> Rs. {float(payload['total_amount']):.2f}</p>
      <p style="color:#888;">Thank you for using StreamHive.</p>
    </div>
    """
    text_body = f"Hi {payload['customer_name']}, your StreamHive booking #{payload['id']} is confirmed. Total: Rs. {float(payload['total_amount']):.2f}"
    return text_body, html_body


def send_booking_receipt_async(payload):
    def worker():
        try:
            with app.app_context():
                if not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"]:
                    return
                msg = Message(
                    f"StreamHive Booking Confirmation #{payload['id']}",
                    sender=app.config["MAIL_USERNAME"],
                    recipients=[payload["customer_email"]],
                )
                text_body, html_body = build_booking_receipt(payload)
                msg.body = text_body
                msg.html = html_body
                mail.send(msg)
        except Exception as exc:
            app.logger.exception("Booking receipt email failed: %s", exc)

    threading.Thread(target=worker, daemon=True).start()


@app.route("/api", methods=["GET"])
@app.route("/api/", methods=["GET"])
def api_root():
    return jsonify(
        {
            "message": "StreamHive Core API is running",
            "status": "healthy",
            "service": "core-api",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    ), 200


@app.route("/api/signup/request", methods=["POST"])
def signup_request():
    data = get_json_payload()
    err = require_fields(data, ["username", "email", "password"])
    if err:
        return err

    email = data["email"].strip().lower()
    username = data["username"].strip()
    full_name = data.get("full_name", username).strip() or username
    password = data["password"].strip()
    pw_err = validate_password_strength(password)
    if pw_err:
        return jsonify({"error": pw_err}), 400

    password_hash = generate_password_hash(password)
    otp = str(random.randint(100000, 999999))
    expiry = datetime.now() + timedelta(minutes=10)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email=%s OR username=%s", (email, username))
            if cursor.fetchone():
                return jsonify({"error": "User already exists"}), 409
            cursor.execute(
                """
                INSERT INTO pending_signups (email, username, full_name, password_hash, otp_code, otp_expiry)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE username=VALUES(username), full_name=VALUES(full_name),
                    password_hash=VALUES(password_hash), otp_code=VALUES(otp_code), otp_expiry=VALUES(otp_expiry)
                """,
                (email, username, full_name, password_hash, otp, expiry),
            )
            conn.commit()
        if app.config["MAIL_USERNAME"]:
            msg = Message("StreamHive - Verify Your Account", sender=app.config["MAIL_USERNAME"], recipients=[email])
            msg.body = f"Hello {username}, your StreamHive signup OTP is {otp}. It expires in 10 minutes."
            mail.send(msg)
        return jsonify({"message": "OTP sent to email!"}), 200
    except Exception as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()


@app.route("/api/signup/verify", methods=["POST"])
def signup_verify():
    data = get_json_payload()
    err = require_fields(data, ["email", "otp"])
    if err:
        return err
    email = data["email"].strip().lower()
    otp = data["otp"].strip()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM pending_signups WHERE email=%s", (email,))
            pending = cursor.fetchone()
            if not pending:
                return jsonify({"error": "Signup request not found"}), 404
            if pending["otp_code"] != otp or datetime.now() >= pending["otp_expiry"]:
                return jsonify({"error": "Invalid or expired OTP"}), 401
            cursor.execute(
                "INSERT INTO users (username, full_name, email, password) VALUES (%s,%s,%s,%s)",
                (pending["username"], pending["full_name"], pending["email"], pending["password_hash"]),
            )
            cursor.execute("DELETE FROM pending_signups WHERE email=%s", (email,))
            conn.commit()
            return jsonify({"message": "Account created!", "user": {"username": pending["username"], "email": email}}), 201
    except pymysql.MySQLError:
        conn.rollback()
        return jsonify({"error": "User already exists"}), 409
    finally:
        conn.close()


@app.route("/api/login/request", methods=["POST"])
def login_request():
    data = get_json_payload()
    err = require_fields(data, ["email", "password"])
    if err:
        return err
    email = data["email"].strip().lower()
    password = data["password"].strip()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cursor.fetchone()
            if not user or not check_password_hash(user["password"], password):
                return jsonify({"error": "Invalid credentials"}), 401

            if not should_require_daily_login_otp(user):
                return jsonify({"message": "Login successful", "otp_required": False, "user": {
                    "id": user["id"], "username": user["username"], "email": user["email"]}}), 200

            otp = str(random.randint(100000, 999999))
            expiry = datetime.now() + timedelta(minutes=5)
            cursor.execute("UPDATE users SET otp_code=%s, otp_expiry=%s WHERE email=%s", (otp, expiry, email))
            conn.commit()
        if app.config["MAIL_USERNAME"]:
            msg = Message("StreamHive - Login OTP", sender=app.config["MAIL_USERNAME"], recipients=[email])
            msg.body = f"Your StreamHive login OTP is {otp}. It expires in 5 minutes."
            mail.send(msg)
        return jsonify({"message": "OTP sent", "otp_required": True}), 200
    except Exception as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()


@app.route("/api/login/verify", methods=["POST"])
def login_verify():
    data = get_json_payload()
    err = require_fields(data, ["email", "otp"])
    if err:
        return err
    email = data["email"].strip().lower()
    otp = data["otp"].strip()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE email=%s AND otp_code=%s", (email, otp))
            user = cursor.fetchone()
            if not user or datetime.now() >= user["otp_expiry"]:
                return jsonify({"error": "Invalid or expired OTP"}), 401
            cursor.execute(
                "UPDATE users SET otp_code=NULL, otp_expiry=NULL, last_login_otp_verified_at=%s WHERE id=%s",
                (datetime.now(), user["id"]),
            )
            conn.commit()
            return jsonify({"message": "Login successful", "user": {
                "id": user["id"], "username": user["username"], "email": user["email"]}}), 200
    finally:
        conn.close()


@app.route("/api/watchlist", methods=["GET"])
def get_watchlist():
    email = request.args.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            user = fetch_user_by_email(cursor, email)
            if not user:
                return jsonify({"error": "User not found"}), 404
            return jsonify(fetch_watchlist(cursor, user["id"])), 200
    finally:
        conn.close()


@app.route("/api/watchlist/items", methods=["POST"])
def add_watchlist_item():
    data = get_json_payload()
    err = require_fields(data, ["email", "item_id", "item_title", "price", "category"])
    if err:
        return err
    email = data["email"].strip().lower()
    quantity = max(int(data.get("quantity", 1)), 1)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            user = fetch_user_by_email(cursor, email)
            if not user:
                return jsonify({"error": "User not found"}), 404
            cursor.execute(
                """
                INSERT INTO watchlist_items (user_id, item_id, item_title, item_thumbnail, category, price, quantity)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE item_title=VALUES(item_title), item_thumbnail=VALUES(item_thumbnail),
                    category=VALUES(category), price=VALUES(price), quantity=quantity+VALUES(quantity)
                """,
                (user["id"], str(data["item_id"]).strip(), str(data["item_title"]).strip(),
                 str(data.get("item_thumbnail", "")).strip() or None, str(data["category"]).strip(),
                 float(data["price"]), quantity),
            )
            conn.commit()
            return jsonify({"message": "Item added to watchlist"}), 201
    finally:
        conn.close()


@app.route("/api/bookings", methods=["POST"])
def create_booking():
    data = get_json_payload()
    err = require_fields(data, ["email", "customer_name"])
    if err:
        return err
    email = data["email"].strip().lower()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_booking_tables(cursor)
            user = fetch_user_by_email(cursor, email)
            if not user:
                return jsonify({"error": "User not found"}), 404

            watchlist = fetch_watchlist(cursor, user["id"])
            items = watchlist["items"]
            if not items:
                return jsonify({"error": "Watchlist is empty"}), 400
            total = watchlist["total"]

            cursor.execute(
                """
                INSERT INTO bookings (user_id, customer_name, customer_email, delivery_address, customer_phone, total_amount, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (user["id"], data["customer_name"], email, data.get("delivery_address"),
                 data.get("customer_phone"), total, data.get("status", "confirmed")),
            )
            booking_id = cursor.lastrowid
            for item in items:
                cursor.execute(
                    """
                    INSERT INTO booking_items (booking_id, item_id, item_title, item_thumbnail, price, quantity)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (booking_id, item["item_id"], item["item_title"], item["item_thumbnail"], item["price"], item["quantity"]),
                )
            cursor.execute("DELETE FROM watchlist_items WHERE user_id=%s", (user["id"],))
            conn.commit()

            payload = {
                "id": booking_id, "customer_name": data["customer_name"], "customer_email": email,
                "total_amount": total, "items": items,
            }
            send_booking_receipt_async(payload)
            return jsonify({"message": "Booking confirmed", "booking_id": booking_id, "total_amount": total}), 201
    except Exception as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()


@app.route("/api/wallet/topups", methods=["POST"])
def create_wallet_topup():
    data = get_json_payload()
    err = require_fields(data, ["email", "amount", "payment_method"])
    if err:
        return err
    email = data["email"].strip().lower()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS wallet_topups (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    payment_method VARCHAR(50) NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'success',
                    transaction_reference VARCHAR(100) DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_topup_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            user = fetch_user_by_email(cursor, email)
            if not user:
                return jsonify({"error": "User not found"}), 404
            cursor.execute(
                "INSERT INTO wallet_topups (user_id, amount, payment_method, status, transaction_reference) VALUES (%s,%s,%s,%s,%s)",
                (user["id"], float(data["amount"]), data["payment_method"], data.get("status", "success"),
                 data.get("transaction_reference")),
            )
            conn.commit()
            return jsonify({"message": "Wallet topped up", "topup_id": cursor.lastrowid}), 201
    finally:
        conn.close()


@app.route("/api/activity", methods=["POST"])
def log_activity():
    data = get_json_payload()
    err = require_fields(data, ["email", "app_name"])
    if err:
        return err
    email = data["email"].strip().lower()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_activity_table(cursor)
            user = fetch_user_by_email(cursor, email)
            if not user:
                return jsonify({"error": "User not found"}), 404
            cursor.execute(
                "INSERT INTO activity_log (user_id, app_name, app_path, activity_type, note) VALUES (%s,%s,%s,%s,%s)",
                (user["id"], data["app_name"], data.get("app_path"), data.get("activity_type", "open"), data.get("note")),
            )
            conn.commit()
            return jsonify({"message": "Activity logged"}), 201
    finally:
        conn.close()


@app.route("/api/history", methods=["GET"])
def get_history():
    email = request.args.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            ensure_booking_tables(cursor)
            ensure_activity_table(cursor)
            user = fetch_user_by_email(cursor, email)
            if not user:
                return jsonify({"error": "User not found"}), 404

            cursor.execute("SELECT * FROM bookings WHERE user_id=%s ORDER BY created_at DESC", (user["id"],))
            bookings = cursor.fetchall()
            cursor.execute("SELECT * FROM activity_log WHERE user_id=%s ORDER BY created_at DESC", (user["id"],))
            activity = cursor.fetchall()
            return jsonify({"bookings": bookings, "activity": activity}), 200
    finally:
        conn.close()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
