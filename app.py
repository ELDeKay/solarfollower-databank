from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta
import psycopg2
import os
import random

app = Flask(__name__)
CORS(app)

# =======================
# Datenbank (PostgreSQL)
# =======================
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL)

# Pico sendet alle 5 Sekunden
PICO_INTERVAL_SECONDS = 5.0

# -----------------------
# DB Initialisierung
# -----------------------
def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS messungen
        (
            id SERIAL PRIMARY KEY,
            watt REAL,
            zeit TIMESTAMP
        )
        """
    )

    # neue Spalte für Energie (kWh)
    c.execute("ALTER TABLE messungen ADD COLUMN IF NOT EXISTS kwh REAL")

    conn.commit()
    conn.close()

# -----------------------
# Simulation (optional)
# -----------------------
def simulate_data():
    """
    - 1 Wert pro Stunde
    - watt = Rohleistung
    - kwh = watt * 1h / 1000
    - <10W wird ignoriert
    """
    conn = get_db()
    c = conn.cursor()
    start = datetime.now() - timedelta(days=365)

    for d in range(365):
        if random.random() < 0.2:
            continue

        for h in range(24):
            t = start + timedelta(days=d, hours=h)
            watt = random.randint(5, 100)

            if watt < 10:
                continue

            kwh = float(watt) / 1000.0

            c.execute(
                "INSERT INTO messungen (watt, kwh, zeit) VALUES (%s, %s, %s)",
                (float(watt), kwh, t)
            )

    conn.commit()
    conn.close()

init_db()

# Simulation nur bei leerer DB
conn = get_db()
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM messungen")
if c.fetchone()[0] == 0:
    simulate_data()
conn.close()

# =======================
# Pico → DB
# =======================
@app.route("/api/pico", methods=["POST"])
def pico_data():
    data = request.get_json()

    if not data or "watt" not in data:
        return jsonify({"error": "watt fehlt"}), 400

    try:
        watt = float(data["watt"])
    except (ValueError, TypeError):
        return jsonify({"error": "ungültiger watt-Wert"}), 400

    if watt < 10.0:
        return jsonify({"status": "ignored", "reason": "watt < 10"}), 200

    # kWh pro 5 Sekunden
    kwh = watt * (PICO_INTERVAL_SECONDS / 3600.0) / 1000.0
    zeit = datetime.now()

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO messungen (watt, kwh, zeit) VALUES (%s, %s, %s)",
        (watt, kwh, zeit)
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"}), 201

# =======================
# Aktueller Watt-Wert
# =======================
@app.route("/api/watt_now")
def watt_now():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT zeit, watt FROM messungen ORDER BY zeit DESC LIMIT 1")
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"zeit": None, "watt": None})

    z, w = row
    return jsonify({"zeit": z.isoformat(), "watt": float(w)})

# =======================
# API Endpunkte (GET)
# =======================
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
    return jsonify(query_monthly_half(start))

# =======================
# Query-Funktionen
# =======================
def query_raw(start):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT zeit, watt FROM messungen WHERE zeit >= %s ORDER BY zeit",
        (start,)
    )
    rows = c.fetchall()
    conn.close()

    return [{"zeit": z.isoformat(), "watt": float(w)} for z, w in rows]

def query_daily(start):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT DATE(zeit) AS tag, COALESCE(SUM(kwh), 0)
        FROM messungen
        WHERE zeit >= %s
        GROUP BY tag
        ORDER BY tag
        """,
        (start,)
    )
    rows = c.fetchall()
    conn.close()

    data = {tag: round(float(s), 6) for tag, s in rows}

    total_days = [
        (start + timedelta(days=i)).date()
        for i in range((datetime.now().date() - start.date()).days + 1)
    ]

    return [{"zeit": d.isoformat(), "watt": data.get(d, 0.0)} for d in total_days]

def query_monthly_half(start):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT
            to_char(zeit, 'YYYY-MM') AS monat,
            CASE
                WHEN EXTRACT(DAY FROM zeit) <= 15 THEN 1
                ELSE 2
            END AS halbmonat,
            COALESCE(SUM(kwh), 0)
        FROM messungen
        WHERE zeit >= %s
        GROUP BY monat, halbmonat
        ORDER BY monat, halbmonat
        """,
        (start,)
    )
    rows = c.fetchall()
    conn.close()

    return [
        {"zeit": f"{monat}-{halbmonat}", "watt": round(float(s), 6)}
        for monat, halbmonat, s in rows
    ]

# =======================
# Start
# =======================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
