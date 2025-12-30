from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import sqlite3
import os

# -------------------------------
# 1️⃣ Flask-Objekt erstellen
# -------------------------------
app = Flask(__name__)
CORS(app)

# -------------------------------
# 2️⃣ SQLite initialisieren
# -------------------------------
def init_db():
    conn = sqlite3.connect("solar.db")
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

init_db()

# -------------------------------
# 3️⃣ GET-Endpunkt Watt
# -------------------------------
@app.route("/api/watt", methods=["GET"])
def get_watt():
    conn = sqlite3.connect("solar.db")
    cursor = conn.cursor()
    cursor.execute("SELECT zeit, watt FROM messungen ORDER BY zeit ASC")
    daten = cursor.fetchall()
    conn.close()
    return jsonify([{"zeit": z, "watt": w} for z, w in daten])

# -------------------------------
# 4️⃣ POST-Endpunkt für Pico-Daten
# -------------------------------
@app.route("/api/watt", methods=["POST"])
def receive_watt():
    data = request.get_json()
    watt = data.get("watt")
    if watt is None:
        return jsonify({"error": "watt fehlt"}), 400
    conn = sqlite3.connect("solar.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messungen (watt, zeit) VALUES (?, ?)",
        (watt, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"}), 200

# -------------------------------
# 5️⃣ Server starten
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
