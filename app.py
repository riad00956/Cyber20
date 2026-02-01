import os
import sqlite3
import subprocess
import threading
from flask import Flask, render_template, request, session, redirect
from flask_socketio import SocketIO, emit

# =====================
# BASIC CONFIG
# =====================
app = Flask(__name__)
app.config["SECRET_KEY"] = "cyber_secret_key"
socketio = SocketIO(app, cors_allowed_origins="*")

DB_FILE = "data.db"
BASE_DIR = "my_projects"

os.makedirs(BASE_DIR, exist_ok=True)

# =====================
# DATABASE INIT
# =====================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        message TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# =====================
# HELPERS
# =====================
def user_dir(uid):
    path = os.path.join(BASE_DIR, f"user_{uid}")
    os.makedirs(path, exist_ok=True)
    return path

def save_log(uid, msg):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO logs (user_id, message) VALUES (?,?)", (uid, msg))
    conn.commit()
    conn.close()

# =====================
# ROUTES
# =====================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=? AND password=?", (u, p))
        user = c.fetchone()
        conn.close()

        if user:
            session["user_id"] = user[0]
            session["username"] = u
            return redirect("/")

    return render_template("index.html", logged_in=("user_id" in session))

@app.route("/register", methods=["POST"])
def register():
    u = request.form.get("username")
    p = request.form.get("password")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username,password) VALUES (?,?)", (u, p))
        conn.commit()
    except:
        pass
    conn.close()
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# =====================
# SOCKET EVENTS
# =====================
@socketio.on("save_and_run")
def save_and_run(data):
    if "user_id" not in session:
        return

    uid = session["user_id"]
    filename = data.get("filename", "main.py")
    code = data.get("code", "")

    path = os.path.join(user_dir(uid), filename)

    with open(path, "w", encoding="utf-8") as f:
        f.write(code)

    emit("log", f"🚀 Running {filename}")
    save_log(uid, f"RUN {filename}")

    def run():
        proc = subprocess.Popen(
            ["python", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in proc.stdout:
            emit("log", line.strip(), to=request.sid)
            save_log(uid, line.strip())

    threading.Thread(target=run).start()

@socketio.on("execute_command")
def execute_command(data):
    if "user_id" not in session:
        return

    uid = session["user_id"]
    cmd = data.get("command")

    emit("log", f"$ {cmd}")
    save_log(uid, cmd)

    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=user_dir(uid),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    for line in proc.stdout:
        emit("log", line.strip(), to=request.sid)
        save_log(uid, line.strip())

# =====================
# MAIN
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port)
