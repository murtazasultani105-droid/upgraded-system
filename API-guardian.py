from fastapi import FastAPI, Request, HTTPException
from datetime import datetime, timedelta
import sqlite3
import threading
import time

app = FastAPI(title="API Guardian")

DB_NAME = "guardian.db"
RATE_LIMIT = 60  # requests
WINDOW_SECONDS = 60
BLOCK_TIME = 300  # seconds


# -------------------- Database --------------------
def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            ip TEXT PRIMARY KEY,
            tokens INTEGER,
            last_request TEXT,
            blocked_until TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            endpoint TEXT,
            timestamp TEXT,
            status TEXT
        )
    """)

    db.commit()
    db.close()


init_db()


# -------------------- Helpers --------------------
def now():
    return datetime.utcnow()


def is_blocked(client):
    if client["blocked_until"] is None:
        return False
    return now() < datetime.fromisoformat(client["blocked_until"])


def refill_tokens(client):
    last = datetime.fromisoformat(client["last_request"])
    elapsed = (now() - last).seconds

    refill = (elapsed * RATE_LIMIT) // WINDOW_SECONDS
    if refill > 0:
        client["tokens"] = min(RATE_LIMIT, client["tokens"] + refill)
        client["last_request"] = now().isoformat()


# -------------------- Client Management --------------------
def get_or_create_client(ip: str):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM clients WHERE ip=?", (ip,))
    client = cursor.fetchone()

    if client is None:
        cursor.execute("""
            INSERT INTO clients (ip, tokens, last_request, blocked_until)
            VALUES (?, ?, ?, ?)
        """, (ip, RATE_LIMIT, now().isoformat(), None))
        db.commit()

        cursor.execute("SELECT * FROM clients WHERE ip=?", (ip,))
        client = cursor.fetchone()

    db.close()
    return dict(client)


def update_client(client):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        UPDATE clients
        SET tokens=?, last_request=?, blocked_until=?
        WHERE ip=?
    """, (
        client["tokens"],
        client["last_request"],
        client["blocked_until"],
        client["ip"]
    ))

    db.commit()
    db.close()


# -------------------- Logger --------------------
def log_request(ip, endpoint, status):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO logs (ip, endpoint, timestamp, status)
        VALUES (?, ?, ?, ?)
    """, (ip, endpoint, now().isoformat(), status))

    db.commit()
    db.close()


# -------------------- Middleware --------------------
@app.middleware("http")
async def rate_limit_guard(request: Request, call_next):
    ip = request.client.host
    endpoint = request.url.path

    client = get_or_create_client(ip)

    if is_blocked(client):
        log_request(ip, endpoint, "BLOCKED")
        raise HTTPException(status_code=429, detail="IP temporarily blocked")

    refill_tokens(client)

    if client["tokens"] <= 0:
        client["blocked_until"] = (now() + timedelta(seconds=BLOCK_TIME)).isoformat()
        update_client(client)
        log_request(ip, endpoint, "BLOCKED")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    client["tokens"] -= 1
    client["last_request"] = now().isoformat()
    update_client(client)

    response = await call_next(request)
    log_request(ip, endpoint, "OK")
    return response


# -------------------- Test Endpoints --------------------
@app.get("/public")
def public_api():
    return {"message": "Public API response"}


@app.get("/stats")
def stats():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM logs")
    total = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) as blocked
        FROM logs WHERE status='BLOCKED'
    """)
    blocked = cursor.fetchone()["blocked"]

    db.close()

    return {
        "total_requests": total,
        "blocked_requests": blocked
    }


@app.get("/clients")
def clients():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM clients")
    data = [dict(row) for row in cursor.fetchall()]
    db.close()
    return data