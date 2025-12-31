from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3, os, random

app = Flask(__name__)
CORS(app)

DB_FILE = "solar.db"

# -----------------------
# DB Initialisierung
# -----------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS messungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watt REAL,
            zeit TEXT
        )
    """)
    conn.commit()
    conn.close()

def simulate_data():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    start = datetime.now() - timedelta(days=365)
    for d in range(365):
        for h in range(24):
            t = start + timedelta(days=d, hours=h)
            watt = random.randint(5, 100)
            c.execute(
                "INSERT INTO messungen (watt, zeit) VALUES (?, ?)",
                (watt, t.isoformat())
            )
    conn.commit()
    conn.close()

init_db()

conn = sqlite3.connect(DB_FILE)
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM messungen")
if c.fetchone()[0] == 0:
    simulate_data()
conn.close()

# -----------------------
# Endpunkte
# -----------------------
@app.route("/api/watt_24h")
def watt_24h():
    start = datetime.now() - timedelta(hours=24)
    return jsonify(query_raw(start))

@app.route("/api/watt_7d")
def watt_7d():
    start = datetime.now() - timedelta(days=7)
    return jsonify(query_daily(start))

@app.route("/api/watt_30d")
def watt_30d():
    start = datetime.now() - timedelta(days=30)
    return jsonify(query_daily(start))

@app.route("/api/watt_12monate")
def watt_12monate():
    start = datetime.now() - timedelta(days=365)
    return jsonify(query_monthly(start))

# -----------------------
# Query-Funktionen
# -----------------------
def query_raw(start):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT zeit, watt FROM messungen WHERE zeit >= ? ORDER BY zeit",
        (start.isoformat(),)
    )
    rows = c.fetchall()
    conn.close()
    return [{"zeit": z, "watt": w} for z, w in rows]

def query_daily(start):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT DATE(zeit) as tag, AVG(watt)
        FROM messungen
        WHERE zeit >= ?
        GROUP BY tag
        ORDER BY tag
    """, (start.isoformat(),))
    rows = c.fetchall()
    conn.close()
    return [{"zeit": t, "watt": round(w, 2)} for t, w in rows]

def query_monthly(start):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT strftime('%Y-%m', zeit) as monat, AVG(watt)
        FROM messungen
        WHERE zeit >= ?
        GROUP BY monat
        ORDER BY monat
    """, (start.isoformat(),))
    rows = c.fetchall()
    conn.close()
    return [{"zeit": m, "watt": round(w, 2)} for m, w in rows]

# -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
