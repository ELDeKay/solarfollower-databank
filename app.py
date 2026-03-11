from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta
import psycopg2
import os

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL fehlt in den Environment-Variablen")

def get_db():
    return psycopg2.connect(DATABASE_URL)

PICO_INTERVAL_SECONDS = 5.0

FIXED_KWH_DATA = [
    ("15.02.2026", 0.33),
    ("16.02.2026", 0.42),
    ("17.02.2026", 0.30),
    ("18.02.2026", 0.61),
    ("19.02.2026", 0.37),
    ("20.02.2026", 0.49),
    ("21.02.2026", 0.52),
    ("22.02.2026", 0.71),
    ("23.02.2026", 0.55),
    ("24.02.2026", 0.95),
    ("25.02.2026", 1.93),
    ("26.02.2026", 2.36),
    ("27.02.2026", 2.78),
    ("28.02.2026", 2.11),
    ("01.03.2026", 2.10),
    ("02.03.2026", 2.34),
    ("03.03.2026", 2.79),
    ("04.03.2026", 2.41),
    ("05.03.2026", 2.41),
    ("06.03.2026", 2.62),
    ("07.03.2026", 3.09),
    ("08.03.2026", 2.99),
    ("09.03.2026", 0.00),
]

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS messungen
        (
            id SERIAL PRIMARY KEY,
            watt REAL,
            zeit TIMESTAMP,
            kwh REAL
        )
        """
    )

    c.execute("ALTER TABLE messungen ADD COLUMN IF NOT EXISTS kwh REAL")

    conn.commit()
    conn.close()

def seed_fixed_data():
    conn = get_db()
    c = conn.cursor()

    c.execute("DELETE FROM messungen")

    for date_str, kwh_value in FIXED_KWH_DATA:
        tag = datetime.strptime(date_str, "%d.%m.%Y")
        c.execute(
            "INSERT INTO messungen (watt, kwh, zeit) VALUES (%s, %s, %s)",
            (None, kwh_value, tag)
        )

    conn.commit()
    conn.close()

def query_hourly_kwh(start):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT DATE_TRUNC('hour', zeit) AS stunde, COALESCE(SUM(kwh), 0)
        FROM messungen
        WHERE zeit >= %s
        GROUP BY stunde
        ORDER BY stunde
        """,
        (start,)
    )
    rows = c.fetchall()
    conn.close()

    data = {stunde: round(float(s), 6) for stunde, s in rows}

    start_hour = start.replace(minute=0, second=0, microsecond=0)
    now_hour = datetime.now().replace(minute=0, second=0, microsecond=0)

    total_hours = []
    t = start_hour
    while t <= now_hour:
        total_hours.append(t)
        t += timedelta(hours=1)

    return [{"zeit": h.isoformat(), "watt": data.get(h, 0.0)} for h in total_hours]

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

@app.route("/")
def home():
    return "Backend läuft"

@app.route("/api/watt_now")
def watt_now():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT zeit, kwh FROM messungen ORDER BY zeit DESC LIMIT 1")
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"zeit": None, "watt": None})

    z, k = row
    return jsonify({"zeit": z.isoformat(), "watt": float(k)})

@app.route("/api/watt_24h")
def watt_24h():
    start = datetime.now() - timedelta(hours=24)
    return jsonify(query_hourly_kwh(start))

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

init_db()
seed_fixed_data()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

