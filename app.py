from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timezone
import psycopg2
import os


app = Flask(__name__)


# =========================================================
# CORS
# =========================================================

CORS(app, resources={
    r"/api/*": {
        "origins": [
            "https://mysolarfollower.onrender.com"
        ]
    }
})


# =========================================================
# PostgreSQL-Verbindung
# =========================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL fehlt in den Environment-Variablen"
    )


def get_db():
    """Öffnet eine neue Verbindung zur PostgreSQL-Datenbank."""

    return psycopg2.connect(DATABASE_URL)


# =========================================================
# Tabellen und Indizes erstellen
# =========================================================

def init_db():
    """Erstellt die Tabellen für Rohdaten und Stundenwerte."""

    conn = get_db()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS roh_messungen
            (
                id BIGSERIAL PRIMARY KEY,
                zeit TIMESTAMPTZ NOT NULL,
                helligkeit DOUBLE PRECISION NOT NULL,
                luftfeucht DOUBLE PRECISION NOT NULL,
                temperatur DOUBLE PRECISION NOT NULL,
                status_tag_nacht BOOLEAN NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS stundenwerte
            (
                stunde TIMESTAMPTZ PRIMARY KEY,
                helligkeit DOUBLE PRECISION NOT NULL,
                luftfeucht DOUBLE PRECISION NOT NULL,
                temperatur DOUBLE PRECISION NOT NULL,
                status_tag_nacht BOOLEAN NOT NULL,
                anzahl_messungen INTEGER NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_roh_messungen_zeit
            ON roh_messungen (zeit)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_stundenwerte_stunde
            ON stundenwerte (stunde)
            """
        )

        conn.commit()

    finally:
        conn.close()


# =========================================================
# Abgeschlossene Stunden verarbeiten
# =========================================================

def abgeschlossene_stunden_verarbeiten(aktuelle_stunde):
    """
    Berechnet Stundenwerte, löscht verarbeitete Rohdaten
    und behält nur die letzten 30 Tage.
    """

    conn = get_db()

    try:
        cursor = conn.cursor()

        # Verhindert eine parallele Berechnung derselben Stunde.
        cursor.execute(
            "SELECT pg_advisory_xact_lock(572934)"
        )

        cursor.execute(
            """
            INSERT INTO stundenwerte
            (
                stunde,
                helligkeit,
                luftfeucht,
                temperatur,
                status_tag_nacht,
                anzahl_messungen
            )

            SELECT
                DATE_TRUNC('hour', zeit),
                AVG(helligkeit),
                AVG(luftfeucht),
                AVG(temperatur),

                (
                    AVG(
                        CASE
                            WHEN status_tag_nacht = TRUE
                            THEN 1.0
                            ELSE 0.0
                        END
                    ) >= 0.5
                ),

                COUNT(*)

            FROM roh_messungen

            WHERE zeit < %s

            GROUP BY DATE_TRUNC('hour', zeit)

            ON CONFLICT (stunde)
            DO UPDATE SET
                helligkeit =
                    EXCLUDED.helligkeit,

                luftfeucht =
                    EXCLUDED.luftfeucht,

                temperatur =
                    EXCLUDED.temperatur,

                status_tag_nacht =
                    EXCLUDED.status_tag_nacht,

                anzahl_messungen =
                    EXCLUDED.anzahl_messungen
            """,
            (aktuelle_stunde,)
        )

        cursor.execute(
            """
            DELETE FROM roh_messungen
            WHERE zeit < %s
            """,
            (aktuelle_stunde,)
        )

        cursor.execute(
            """
            DELETE FROM stundenwerte
            WHERE stunde < %s - INTERVAL '30 days'
            """,
            (aktuelle_stunde,)
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# =========================================================
# Eingabewerte prüfen
# =========================================================

def ist_zahl(wert):
    """Prüft Zahlenwerte und schließt Boolean-Werte aus."""

    return (
        isinstance(wert, (int, float))
        and not isinstance(wert, bool)
    )


# =========================================================
# Messdaten vom Pico empfangen
# =========================================================

@app.route("/api/getdata", methods=["POST"])
def receive_getdata():
    """Prüft und speichert einen neuen 5-Sekunden-Messwert."""

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "Keine gültigen JSON-Daten empfangen"
        }), 400

    erforderliche_felder = [
        "zeit",
        "helligkeit",
        "luftfeucht",
        "temperatur",
        "statusTagNacht"
    ]

    fehlende_felder = [
        feld
        for feld in erforderliche_felder
        if feld not in data
    ]

    if fehlende_felder:
        return jsonify({
            "error": "Erforderliche Felder fehlen",
            "felder": fehlende_felder
        }), 400

    unix_zeit = data.get("zeit")
    helligkeit = data.get("helligkeit")
    luftfeucht = data.get("luftfeucht")
    temperatur = data.get("temperatur")
    status_tag_nacht = data.get("statusTagNacht")


    if not ist_zahl(unix_zeit):
        return jsonify({
            "error": "zeit muss eine Unix-Zeit in Sekunden sein"
        }), 400

    if not ist_zahl(helligkeit):
        return jsonify({
            "error": "helligkeit muss eine Zahl sein"
        }), 400

    if not ist_zahl(luftfeucht):
        return jsonify({
            "error": "luftfeucht muss eine Zahl sein"
        }), 400

    if not ist_zahl(temperatur):
        return jsonify({
            "error": "temperatur muss eine Zahl sein"
        }), 400

    if not isinstance(status_tag_nacht, bool):
        return jsonify({
            "error": "statusTagNacht muss true oder false sein"
        }), 400


    try:
        messzeit = datetime.fromtimestamp(
            float(unix_zeit),
            tz=timezone.utc
        )

    except (ValueError, TypeError, OverflowError):
        return jsonify({
            "error": "Ungültiger Unix-Zeitstempel"
        }), 400


    aktuelle_stunde = messzeit.replace(
        minute=0,
        second=0,
        microsecond=0
    )


    try:
        # Schließt alte Stunden ab, bevor der neue Wert gespeichert wird.
        abgeschlossene_stunden_verarbeiten(
            aktuelle_stunde
        )

        conn = get_db()

        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO roh_messungen
                (
                    zeit,
                    helligkeit,
                    luftfeucht,
                    temperatur,
                    status_tag_nacht
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    messzeit,
                    float(helligkeit),
                    float(luftfeucht),
                    float(temperatur),
                    status_tag_nacht
                )
            )

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    except Exception as fehler:
        print(
            "Fehler beim Speichern der Messdaten:",
            fehler
        )

        return jsonify({
            "error": "Datenbankfehler beim Speichern"
        }), 500


    return jsonify({
        "status": "ok",
        "zeit": int(messzeit.timestamp())
    }), 200


# =========================================================
# Rohdaten der laufenden Stunde ausgeben
# =========================================================

@app.route("/api/data", methods=["GET"])
def get_data():
    """Liefert alle 5-Sekunden-Werte der laufenden Stunde."""

    conn = get_db()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                EXTRACT(EPOCH FROM zeit)::BIGINT,
                helligkeit,
                luftfeucht,
                temperatur,
                status_tag_nacht

            FROM roh_messungen

            ORDER BY zeit ASC
            """
        )

        rows = cursor.fetchall()

    finally:
        conn.close()


    daten = [
        {
            "zeit": int(zeit),
            "helligkeit": float(helligkeit),
            "luftfeucht": float(luftfeucht),
            "temperatur": float(temperatur),
            "statusTagNacht": status_tag_nacht
        }
        for (
            zeit,
            helligkeit,
            luftfeucht,
            temperatur,
            status_tag_nacht
        ) in rows
    ]

    return jsonify(daten), 200


# =========================================================
# Stundenwerte der letzten 30 Tage ausgeben
# =========================================================

@app.route("/api/stundenwerte", methods=["GET"])
def get_stundenwerte():
    """Liefert die berechneten Stundenwerte für die Graphen."""

    conn = get_db()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                EXTRACT(EPOCH FROM stunde)::BIGINT,
                helligkeit,
                luftfeucht,
                temperatur,
                status_tag_nacht,
                anzahl_messungen

            FROM stundenwerte

            ORDER BY stunde ASC
            """
        )

        rows = cursor.fetchall()

    finally:
        conn.close()


    daten = [
        {
            "zeit": int(stunde),

            "helligkeit": round(
                float(helligkeit),
                2
            ),

            "luftfeucht": round(
                float(luftfeucht),
                2
            ),

            "temperatur": round(
                float(temperatur),
                2
            ),

            "statusTagNacht":
                status_tag_nacht,

            "anzahlMessungen":
                anzahl_messungen
        }
        for (
            stunde,
            helligkeit,
            luftfeucht,
            temperatur,
            status_tag_nacht,
            anzahl_messungen
        ) in rows
    ]

    return jsonify(daten), 200


# =========================================================
# Aktuellsten Messwert ausgeben
# =========================================================

@app.route("/api/aktuell", methods=["GET"])
def get_aktueller_wert():
    """Liefert nur den zuletzt empfangenen Messwert."""

    conn = get_db()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                EXTRACT(EPOCH FROM zeit)::BIGINT,
                helligkeit,
                luftfeucht,
                temperatur,
                status_tag_nacht

            FROM roh_messungen

            ORDER BY zeit DESC

            LIMIT 1
            """
        )

        row = cursor.fetchone()

    finally:
        conn.close()


    if row is None:
        return jsonify({
            "zeit": None,
            "helligkeit": None,
            "luftfeucht": None,
            "temperatur": None,
            "statusTagNacht": None
        }), 200


    (
        zeit,
        helligkeit,
        luftfeucht,
        temperatur,
        status_tag_nacht
    ) = row


    return jsonify({
        "zeit": int(zeit),
        "helligkeit": float(helligkeit),
        "luftfeucht": float(luftfeucht),
        "temperatur": float(temperatur),
        "statusTagNacht": status_tag_nacht
    }), 200


# =========================================================
# Statusseite
# =========================================================

@app.route("/")
def home():
    return jsonify({
        "status": "Datenbank-Backend läuft"
    }), 200


# =========================================================
# Initialisierung
# =========================================================

init_db()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
