from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta
import psycopg2
import os

app = Flask(__name__)
CORS(app)

# =======================
# Datenbank (PostgreSQL)
# =======================
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL fehlt in den Environment-Variablen")

def get_db():
    return psycopg2.connect(DATABASE_URL)

# Pico sendet alle 5 Sekunden
PICO_INTERVAL_SECONDS = 5.0

# =======================
# Feste Tagesdaten
# =======================
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
]

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
            zeit TIMESTAMP,
            kwh REAL
        )
        """
    )

    # Falls Tabelle schon existiert und kwh noch fehlt
    c.execute("ALTER TABLE messungen ADD COLUMN IF NOT EXISTS kwh REAL")

    conn.commit()
    conn.close()

# -----------------------
# Feste Daten einsetzen
# -----------------------
def seed_fixed_data():
    conn = get_db()
    c = conn.cursor()

    # Alle bisherigen Zufallsdaten löschen
    c.execute("DELETE FROM messungen")

    # Nur die Werte aus deiner Tabelle einfügen
    for date_str, kwh_value in FIXED_KWH_DATA:
        tag = datetime.strptime(date_str, "%d.%m.%Y")
        c.execute(
            "INSERT INTO messungen (watt, kwh, zeit) VALUES (%s, %s, %s)",
            (None, kwh_value, tag)
        )

    conn.commit()
    conn.close()

init_db()
seed_fixed_data()
