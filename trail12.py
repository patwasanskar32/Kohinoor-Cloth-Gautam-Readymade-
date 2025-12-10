import os
import sqlite3
from datetime import datetime
from functools import wraps
from io import StringIO
import csv

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, Response
)
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode

# ----------------- Paths & Setup -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")
QRCODE_DIR = os.path.join(STATIC_DIR, "qr_codes")

os.makedirs(QRCODE_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = "change_this_secret_key_very_long"


# ----------------- DB Helpers -----------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('owner','staff')),
            qr_filename TEXT
        )
    """)

    # Attendance table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            check_in TEXT NOT NULL,
            check_out TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Messages table (owner -> staff)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            to_user_id INTEGER NOT NULL,
            title TEXT,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(to_user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ----------------- Auth Decorator -----------------
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("Access denied.", "danger")
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ----------------- QR Helper -----------------
def generate_qr_for_user(user_id):
    """QR content: ATTEND:<user_id>"""
    data = f"ATTEND:{user_id}"
    filename = f"user_{user_id}.png"
    filepath = os.path.join(QRCODE_DIR, filename)

    img = qrcode.make(data)
    img.save(filepath)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET qr_filename=? WHERE id=?", (filename, user_id))
    conn.commit()
    conn.close()

    return filename


# ----------------- Routes -----------------

@app.route("/")
def index():
    # If no owner exists, go to owner registration
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM users WHERE role='owner'")
    owner_count = cur.fetchone()["c"]
    conn.close()

    if owner_count == 0:
        return redirect(url_for("register_owner"))

    # If logged in, route to dashboard
    if "user_id" in session:
        if session["role"] == "owner":
            return redirect(url_for("owner_dashboard"))
        else:
            return redirect(url_for("staff_dashboard"))

    return redirect(url_for("login"))


# ----- Owner first-time registration -----
@app.route("/register_owner", methods=["GET", "POST"])
def register_owner():
    # Only allow if no owner exists
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM users WHERE role='owner'")
    owner_count = cur.fetchone()["c"]
    conn.close()

    if owner_count > 0:
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            flash("Username and password required.", "danger")
            return redirect(url_for("register_owner"))

        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'owner')",
                (username, generate_password_hash(password))
            )
            owner_id = cur.lastrowid
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            flash("Username already exists.", "danger")
            return redirect(url_for("register_owner"))

        conn.close()
        generate_qr_for_user(owner_id)
        flash("Owner created. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register_owner.html")


# ----- Login / Logout -----
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=?", (username,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]

            if user["role"] == "owner":
                return redirect(url_for("owner_dashboard"))
            else:
                return redirect(url_for("staff_dashboard"))
        else:
            flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ----- Owner Dashboard -----
@app.route("/owner_dashboard")
@login_required(role="owner")
def owner_dashboard():
    from_date = request.args.get("from_date") or ""
    to_date = request.args.get("to_date") or ""

    conn = get_db()
    cur = conn.cursor()

    # Users with today status
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
        SELECT
          u.id,
          u.username,
          u.role,
          u.qr_filename,
          CASE
            WHEN EXISTS (
              SELECT 1 FROM attendance a
              WHERE a.user_id = u.id
                AND substr(a.check_in,1,10) = ?
            ) THEN 'Present'
            ELSE 'Absent'
          END AS today_status
        FROM users u
        ORDER BY u.role, u.username
    """, (today,))
    users = cur.fetchall()

    # Attendance with filters
    query = """
        SELECT u.username, a.check_in, a.check_out
        FROM attendance a
        JOIN users u ON u.id = a.user_id
        WHERE 1=1
    """
    params = []
    if from_date:
        query += " AND substr(a.check_in,1,10) >= ?"
        params.append(from_date)
    if to_date:
        query += " AND substr(a.check_in,1,10) <= ?"
        params.append(to_date)
    query += " ORDER BY a.check_in DESC"

    cur.execute(query, params)
    attendance = cur.fetchall()
    conn.close()

    return render_template(
        "owner_dashboard.html",
        users=users,
        attendance=attendance,
        from_date=from_date,
        to_date=to_date
    )


# ----- Export attendance CSV -----
@app.route("/export_attendance")
@login_required(role="owner")
def export_attendance():
    from_date = request.args.get("from_date") or ""
    to_date = request.args.get("to_date") or ""

    conn = get_db()
    cur = conn.cursor()
    query = """
        SELECT u.username, u.role, a.check_in, a.check_out
        FROM attendance a
        JOIN users u ON u.id = a.user_id
        WHERE 1=1
    """
    params = []
    if from_date:
        query += " AND substr(a.check_in,1,10) >= ?"
        params.append(from_date)
    if to_date:
        query += " AND substr(a.check_in,1,10) <= ?"
        params.append(to_date)
    query += " ORDER BY a.check_in DESC"

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["username", "role", "check_in", "check_out"])
    for r in rows:
        writer.writerow([r["username"], r["role"], r["check_in"], r["check_out"] or ""])
    csv_data = output.getvalue()
    output.close()

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=attendance_export.csv"}
    )


# ----- Manage Staff -----
@app.route("/manage_staff", methods=["GET", "POST"])
@login_required(role="owner")
def manage_staff():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add":
            username = request.form["username"].strip()
            password = request.form["password"]
            if not username or not password:
                flash("Username and password required.", "danger")
                return redirect(url_for("manage_staff"))
            try:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'staff')",
                    (username, generate_password_hash(password))
                )
                staff_id = cur.lastrowid
                conn.commit()
                generate_qr_for_user(staff_id)
                flash(f"Staff '{username}' added.", "success")
            except sqlite3.IntegrityError:
                flash("Username already exists.", "danger")

        elif action == "delete":
            user_id = int(request.form["user_id"])
            cur.execute("SELECT username, qr_filename FROM users WHERE id=? AND role='staff'", (user_id,))
            user = cur.fetchone()
            if user:
                # delete QR file
                if user["qr_filename"]:
                    path = os.path.join(QRCODE_DIR, user["qr_filename"])
                    if os.path.exists(path):
                        os.remove(path)
                # delete attendance & messages & user
                cur.execute("DELETE FROM attendance WHERE user_id=?", (user_id,))
                cur.execute("DELETE FROM messages WHERE to_user_id=?", (user_id,))
                cur.execute("DELETE FROM users WHERE id=?", (user_id,))
                conn.commit()
                flash(f"Staff '{user['username']}' deleted.", "info")

        conn.close()
        return redirect(url_for("manage_staff"))

    cur.execute("SELECT id, username FROM users WHERE role='staff' ORDER BY username")
    staff = cur.fetchall()
    conn.close()
    return render_template("manage_staff.html", staff=staff)


# ----- QR Scan (Owner) -----
@app.route("/scan_qr", methods=["GET", "POST"])
@login_required(role="owner")
def scan_qr():
    if request.method == "POST":
        qr_value = request.form["qr_value"].strip()
        if not qr_value.startswith("ATTEND:"):
            flash("Invalid QR value.", "danger")
            return redirect(url_for("scan_qr"))

        try:
            user_id = int(qr_value.split(":", 1)[1])
        except ValueError:
            flash("Invalid QR value.", "danger")
            return redirect(url_for("scan_qr"))

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, username, role FROM users WHERE id=?", (user_id,))
        user = cur.fetchone()
        if not user or user["role"] != "staff":
            conn.close()
            flash("QR does not belong to a staff member.", "danger")
            return redirect(url_for("scan_qr"))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # open attendance if exists
        cur.execute("""
            SELECT * FROM attendance
            WHERE user_id=? AND check_out IS NULL
            ORDER BY check_in DESC LIMIT 1
        """, (user_id,))
        open_row = cur.fetchone()

        if open_row:
            cur.execute("UPDATE attendance SET check_out=? WHERE id=?", (now, open_row["id"]))
            msg = f"Checked OUT {user['username']} at {now}"
        else:
            cur.execute("INSERT INTO attendance (user_id, check_in) VALUES (?, ?)", (user_id, now))
            msg = f"Checked IN {user['username']} at {now}"

        conn.commit()
        conn.close()
        flash(msg, "success")
        return redirect(url_for("scan_qr"))

    return render_template("scan_qr.html")


# ----- Owner manual attendance (no QR) -----
@app.route("/owner_mark_attendance", methods=["POST"])
@login_required(role="owner")
def owner_mark_attendance():
    staff_id = request.form.get("staff_id")
    if not staff_id:
        flash("Select a staff member.", "danger")
        return redirect(url_for("owner_dashboard"))

    try:
        staff_id = int(staff_id)
    except ValueError:
        flash("Invalid staff selected.", "danger")
        return redirect(url_for("owner_dashboard"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role FROM users WHERE id=?", (staff_id,))
    user = cur.fetchone()
    if not user or user["role"] != "staff":
        conn.close()
        flash("Selected user is not staff.", "danger")
        return redirect(url_for("owner_dashboard"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        SELECT * FROM attendance
        WHERE user_id=? AND check_out IS NULL
        ORDER BY check_in DESC LIMIT 1
    """, (staff_id,))
    open_row = cur.fetchone()

    if open_row:
        cur.execute("UPDATE attendance SET check_out=? WHERE id=?", (now, open_row["id"]))
        msg = f"Checked OUT {user['username']} at {now}"
    else:
        cur.execute("INSERT INTO attendance (user_id, check_in) VALUES (?, ?)", (staff_id, now))
        msg = f"Checked IN {user['username']} at {now}"

    conn.commit()
    conn.close()
    flash(msg, "success")
    return redirect(url_for("owner_dashboard"))


# ----- Owner send message -----
@app.route("/send_message", methods=["POST"])
@login_required(role="owner")
def send_message():
    to_user_id = request.form.get("to_user_id")
    title = request.form.get("title", "").strip()
    body = request.form.get("body", "").strip()

    if not to_user_id or not body:
        flash("Select staff and enter a message.", "danger")
        return redirect(url_for("owner_dashboard"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (to_user_id, title, body, created_at) VALUES (?, ?, ?, ?)",
        (to_user_id, title, body, now)
    )
    conn.commit()
    conn.close()
    flash("Information sent.", "success")
    return redirect(url_for("owner_dashboard"))


# ----- Staff Dashboard -----
@app.route("/staff_dashboard")
@login_required(role="staff")
def staff_dashboard():
    user_id = session["user_id"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT username, qr_filename FROM users WHERE id=?", (user_id,))
    user = cur.fetchone()
    qr_filename = user["qr_filename"]

    if not qr_filename:
        qr_filename = generate_qr_for_user(user_id)

    # Attendance logs
    cur.execute("""
        SELECT check_in, check_out FROM attendance
        WHERE user_id=? ORDER BY check_in DESC LIMIT 30
    """, (user_id,))
    logs = cur.fetchall()

    # Today status
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
        SELECT CASE WHEN EXISTS (
          SELECT 1 FROM attendance WHERE user_id=? AND substr(check_in,1,10)=?
        ) THEN 'Present' ELSE 'Absent' END AS today_status
    """, (user_id, today))
    today_status = cur.fetchone()["today_status"]

    # Messages
    cur.execute("""
        SELECT title, body, created_at FROM messages
        WHERE to_user_id=? ORDER BY created_at DESC LIMIT 20
    """, (user_id,))
    messages = cur.fetchall()

    conn.close()

    return render_template(
        "staff_dashboard.html",
        username=user["username"],
        qr_filename=qr_filename,
        logs=logs,
        messages=messages,
        today_status=today_status
    )


# ----------------- Run -----------------
if __name__ == "__main__":
    app.run(debug=True)
