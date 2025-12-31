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
    """
    Simuliert Messungen für 1 Jahr, aber mit zufälligen Lücken von einigen Tagen,
    damit im Graphen fehlende Daten sichtbar werden.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    start = datetime.now() - timedelta(days=365)
    
    for d in range(365):
        # Simuliere Lücke: 20% der Tage fehlen komplett
        if random.random() < 0.0:
            continue  # diesen Tag überspringen

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
    return jsonify(query_monthly_half(start))

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
    """
    Liefert für jeden Tag ab 'start' einen Wert zurück.
    Falls keine Messung existiert, wird 'watt': None gesetzt,
    damit Chart.js eine Lücke zeigt.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Hol alle vorhandenen Daten
    c.execute("""
        SELECT DATE(zeit) as tag, AVG(watt)
        FROM messungen
        WHERE zeit >= ?
        GROUP BY tag
        ORDER BY tag
    """, (start.isoformat(),))
    rows = c.fetchall()
    conn.close()

    # Alle Tage im Zeitraum
    total_days = [(start + timedelta(days=i)).date() for i in range((datetime.now().date() - start.date()).days + 1)]
    data_dict = {datetime.strptime(tag, "%Y-%m-%d").date(): round(avg, 2) for tag, avg in rows}

    # Fehlende Tage auf None setzen
    result = [{"zeit": d.isoformat(), "watt": data_dict.get(d, None)} for d in total_days]
    return result


def query_monthly_half(start):
    """
    Gibt für jeden Monat zwei Werte zurück: 
    1.-15. des Monats und 16.-Ende des Monats
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT strftime('%Y-%m', zeit) as monat,
               CASE WHEN CAST(strftime('%d', zeit) AS INTEGER) <= 15 THEN 1 ELSE 2 END as halbmonat,
               AVG(watt)
        FROM messungen
        WHERE zeit >= ?
        GROUP BY monat, halbmonat
        ORDER BY monat, halbmonat
    """, (start.isoformat(),))
    rows = c.fetchall()
    conn.close()

    # Erzeuge ein einheitliches Format für die Zeitangabe
    return [
        {"zeit": f"{monat}-{halbmonat}", "watt": round(avg_watt, 2)}
        for monat, halbmonat, avg_watt in rows
    ]

# -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))





