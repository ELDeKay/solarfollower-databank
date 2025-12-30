from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import os
import random

# -------------------------------
# 1️⃣ Flask-Objekt erstellen
# -------------------------------
app = Flask(__name__)
CORS(app)

# -------------------------------
# 2️⃣ SQLite initialisieren
# -------------------------------
DB_FILE = "solar.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
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
    cursor = conn.cursor()
    start = datetime.now() - timedelta(days=365)
    for tag in range(365):
        for stunde in range(24):
            zeitpunkt = start + timedelta(days=tag, hours=stunde)
            watt = random.randint(5, 100)
            cursor.execute(
                "INSERT INTO messungen (watt, zeit) VALUES (?, ?)",
                (watt, zeitpunkt.isoformat())
            )
    conn.commit()
    conn.close()

init_db()

# Daten nur simulieren, wenn DB leer
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM messungen")
anzahl = cursor.fetchone()[0]
conn.close()

if anzahl == 0:
    simulate_data()

# -------------------------------
# Hilfsfunktion: Alte Daten löschen (>365 Tage)
# -------------------------------
def cleanup_old_data():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    ein_jahr_ago = datetime.now() - timedelta(days=365)
    cursor.execute("DELETE FROM messungen WHERE zeit < ?", (ein_jahr_ago.isoformat(),))
    conn.commit()
    conn.close()

# -------------------------------
# 3️⃣ POST-Endpunkt für Pico-Daten
# -------------------------------
@app.route("/api/watt", methods=["POST"])
def receive_watt():
    data = request.get_json()
    watt = data.get("watt")
    if watt is None:
        return jsonify({"error": "watt fehlt"}), 400

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messungen (watt, zeit) VALUES (?, ?)",
        (watt, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    cleanup_old_data()
    return jsonify({"status": "ok"}), 200

# -------------------------------
# 4️⃣ GET-Endpunkte nach Zeitraum mit Aggregation
# -------------------------------
def get_watt_data(days=None, aggregate='hour'):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    if days is None:
        cursor.execute("SELECT zeit, watt FROM messungen ORDER BY zeit ASC")
    else:
        start_time = datetime.now() - timedelta(days=days)
        cursor.execute(
            "SELECT zeit, watt FROM messungen WHERE zeit >= ? ORDER BY zeit ASC",
            (start_time.isoformat(),)
        )

    daten = cursor.fetchall()
    conn.close()

    if aggregate == 'day':
        # Tagesmittel aggregieren
        day_dict = {}
        for z, w in daten:
            tag = z.split("T")[0]  # yyyy-mm-dd
            day_dict.setdefault(tag, []).append(w)
        return [{"zeit": k, "watt": sum(v)/len(v)} for k,v in sorted(day_dict.items())]

    elif aggregate == 'hour':
        # Stundenmittel (jedes einzelne Datenpunkt bleibt)
        return [{"zeit": z, "watt": w} for z, w in daten]

    return [{"zeit": z, "watt": w} for z, w in daten]

@app.route("/api/watt_24h", methods=["GET"])
def watt_24h():
    return jsonify(get_watt_data(1, aggregate='hour'))

@app.route("/api/watt_7d", methods=["GET"])
def watt_7d():
    return jsonify(get_watt_data(7, aggregate='hour'))

@app.route("/api/watt_30d", methods=["GET"])
def watt_30d():
    return jsonify(get_watt_data(30, aggregate='hour'))

@app.route("/api/watt_12monate", methods=["GET"])
def watt_12monate():
    return jsonify(get_watt_data(365, aggregate='day'))

# -------------------------------
# 5️⃣ Server starten
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
