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
init_db()
