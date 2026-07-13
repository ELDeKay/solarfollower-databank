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
# PostgreSQL-Datenbank
# =========================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL fehlt in den Environment-Variablen"
    )


def get_db():
    return psycopg2.connect(DATABASE_URL)


# =========================================================
# Datenbank initialisieren
# =========================================================

def init_db():
    conn = get_db()

    try:
        cursor = conn.cursor()

        # -------------------------------------------------
        # Rohwerte der aktuell laufenden Stunde
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Berechnete Stundenwerte der letzten 30 Tage
        # -------------------------------------------------

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

        # Index für schnellere Zeitabfragen
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
# Abgeschlossene Stunden berechnen
# =========================================================

def abgeschlossene_stunden_verarbeiten(aktuelle_stunde):
    """
    Berechnet alle vollständig abgeschlossenen Stunden.

    aktuelle_stunde ist beispielsweise:

        2026-07-13 20:00:00 UTC

    Alle Rohwerte vor dieser Stunde werden gruppiert,
    als Stundenwerte gespeichert und danach gelöscht.
    """

    conn = get_db()

    try:
        cursor = conn.cursor()

        # Verhindert, dass zwei gleichzeitige Requests
        # dieselbe Stunde parallel verarbeiten.
        cursor.execute(
            "SELECT pg_advisory_xact_lock(572934)"
        )

        # -------------------------------------------------
        # Durchschnittswerte je abgeschlossener Stunde
        # berechnen und speichern
        # -------------------------------------------------

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
                DATE_TRUNC('hour', zeit) AS stunde,

                AVG(helligkeit) AS helligkeit,

                AVG(luftfeucht) AS luftfeucht,

                AVG(temperatur) AS temperatur,

                (
                    AVG(
                        CASE
                            WHEN status_tag_nacht = TRUE
                            THEN 1.0
                            ELSE 0.0
                        END
                    ) >= 0.5
                ) AS status_tag_nacht,

                COUNT(*) AS anzahl_messungen

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

        # -------------------------------------------------
        # Rohwerte abgeschlossener Stunden löschen
        # -------------------------------------------------

        cursor.execute(
            """
            DELETE FROM roh_messungen
            WHERE zeit < %s
            """,
            (aktuelle_stunde,)
        )

        # -------------------------------------------------
        # Nur die letzten 30 Tage behalten
        #
        # 30 Tage × 24 Stunden = maximal 720 Stundenzeilen
        # -------------------------------------------------

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
# Eingabedaten prüfen
# =========================================================

def ist_zahl(wert):
    """
    True und False gelten in Python ebenfalls als int.
    Deshalb werden Boolean-Werte hier ausdrücklich abgelehnt.
    """

    return (
        isinstance(wert, (int, float))
        and not isinstance(wert, bool)
    )


# =========================================================
# POST /api/getdata
#
# Pico sendet alle 5 Sekunden:
#
# {
#   "zeit": 1783964148,
#   "helligkeit": 500,
#   "luftfeucht": 60,
#   "temperatur": 22.5,
#   "statusTagNacht": true
# }
# =========================================================

@app.route("/api/getdata", methods=["POST"])
def receive_getdata():
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

    # -----------------------------------------------------
    # Datentypen prüfen
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Unix-Sekunden in UTC-Datum umwandeln
    # -----------------------------------------------------

    try:
        messzeit = datetime.fromtimestamp(
            float(unix_zeit),
            tz=timezone.utc
        )

    except (ValueError, TypeError, OverflowError):
        return jsonify({
            "error": "Ungültiger Unix-Zeitstempel"
        }), 400

    # Beginn der Stunde bestimmen
    aktuelle_stunde = messzeit.replace(
        minute=0,
        second=0,
        microsecond=0
    )

    try:
        # Zuerst eventuell abgeschlossene alte Stunde
        # berechnen und Rohwerte löschen.
        abgeschlossene_stunden_verarbeiten(
            aktuelle_stunde
        )

        # Danach neuen 5-Sekunden-Wert speichern.
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
# GET /api/data
#
# Liefert alle 5-Sekunden-Werte der aktuell laufenden Stunde.
# Die Website kann daraus den letzten Live-Wert verwenden.
# =========================================================

@app.route("/api/data", methods=["GET"])
def get_data():
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
# GET /api/stundenwerte
#
# Liefert die berechneten Stundenwerte der letzten 30 Tage.
# Maximal 720 Zeilen.
# =========================================================

@app.route("/api/stundenwerte", methods=["GET"])
def get_stundenwerte():
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
            "statusTagNacht": status_tag_nacht,
            "anzahlMessungen": anzahl_messungen
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
# GET /api/aktuell
#
# Liefert nur den zuletzt empfangenen Messwert.
# =========================================================

@app.route("/api/aktuell", methods=["GET"])
def get_aktueller_wert():
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
        "status": "Backend läuft"
    }), 200


# =========================================================
# Datenbank beim Start initialisieren
# =========================================================

init_db()


# =========================================================
# Lokaler Start
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
