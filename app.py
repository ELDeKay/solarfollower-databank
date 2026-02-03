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
    conn.commit()
    conn.close()

# -----------------------
# (OPTIONAL) Simulation
# NUR lokal verwenden!
# -----------------------
def simulate_data():
    conn = get_db()
    c = conn.cursor()
    start = datetime.now() - timedelta(days=365)

    for d in range(365):
        if random.random() < 0.2:
            continue

        for h in range(24):
            t = start + timedelta(days=d, hours=h)
            watt = random.randint(5, 100)
            c.execute(
                    "INSERT INTO messungen (watt, zeit) VALUES (%s, %s)",
                    (watt, t)
            )

    conn.commit()
    conn.close()

init_db()

# ⚠️ Simulation nur wenn DB leer ist
conn = get_db()
c = conn.cursor()
c.execute(
            "SELECT COUNT(*) FROM messungen"
)

if c.fetchone()[0] == 0:
    simulate_data()
conn.close()

# =======================
# 🔥 NEU: Pico → DB
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

    # ✅ Alles unter 5W nicht speichern
    if watt < 5.0:
        return jsonify({"status": "ignored", "reason": "watt < 10"}), 200

    zeit = datetime.now()

    conn = get_db()
    c = conn.cursor()
    c.execute(
            "INSERT INTO messungen (watt, zeit) VALUES (%s, %s)",
            (watt, zeit)
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"}), 201

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

# 24h: statt Rohdaten -> Summen pro Stunde
def query_raw(start):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT date_trunc('hour', zeit) AS stunde, SUM(watt)
        FROM messungen
        WHERE zeit >= %s
        GROUP BY stunde
        ORDER BY stunde
        """,
        (start,)
    )
    rows = c.fetchall()
    conn.close()

    data = {stunde: round(float(s), 2) for stunde, s in rows}

    total_hours = [
        (start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=i))
        for i in range(int((datetime.now() - start).total_seconds() // 3600) + 1)
    ]

    return [
        {"zeit": h.isoformat(), "watt": data.get(h, None)}
        for h in total_hours
    ]

# 7d/30d: statt AVG -> SUM pro Tag
def query_daily(start):
    conn = get_db()
    c = conn.cursor()
    c.execute(
            """
                SELECT DATE(zeit) AS tag, SUM(watt)
                FROM messungen
                WHERE zeit >= %s
                GROUP BY tag
                ORDER BY tag
            """, (start,)
    )
    rows = c.fetchall()
    conn.close()

    data = {tag: round(float(s), 2) for tag, s in rows}

    total_days = [
            (start + timedelta(days=i)).date()
            for i in range((datetime.now().date() - start.date()).days + 1)
    ]

    return [
            {"zeit": d.isoformat(), "watt": data.get(d, None)}
            for d in total_days
    ]

# 12 Monate: statt AVG -> SUM pro Halbmonat
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
            SUM(watt)
            FROM messungen
            WHERE zeit >= %s
            GROUP BY monat, halbmonat
            ORDER BY monat, halbmonat
            """, (start,)
    )
    rows = c.fetchall()
    conn.close()

    return [
            {"zeit": f"{monat}-{halbmonat}", "watt": round(float(s), 2)}
            for monat, halbmonat, s in rows
    ]

# =======================
# Start
# =======================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
