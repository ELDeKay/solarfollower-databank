import sqlite3

def init_db():
    # Erstellt Datei solar.db, falls sie noch nicht existiert
    conn = sqlite3.connect("solar.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wind REAL,
            temperatur REAL,
            watt REAL,
            zeit TEXT
        )
    """)
    conn.commit()
    conn.close()

# gleich beim Start des Backends aufrufen
@app.route("/api/watt", methods=["GET"])
def get_watt():
    conn = sqlite3.connect("solar.db")
    cursor = conn.cursor()
    
    # Nur Zeit und Watt abrufen, sortiert nach Zeit
    cursor.execute("SELECT zeit, watt FROM messungen ORDER BY zeit ASC")
    daten = cursor.fetchall()
    conn.close()

    # In JSON umwandeln
    result = [{"zeit": z, "watt": w} for z, w in daten]
    return jsonify(result)
