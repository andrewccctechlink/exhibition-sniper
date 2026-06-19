"""Exhibition Lead Sniper — Unified Server (Flask)
One server handles everything: frontend + API + AI services.
Deploy as a single Zeabur service from one GitHub repo.
"""

import base64
import json
import logging
import os
import sqlite3
from datetime import datetime

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory

from local_customs import CustomsReader
from pitch_deck import PitchDeckGenerator
from services import gemini, deepseek, enrichment

# ── Configuration ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "sniper.db")
CUSTOMS_PATH = os.path.join(BASE_DIR, "database", "app_customs_data.xlsx")
STORAGE_PATH = os.path.join(BASE_DIR, "storage")
PORT = int(os.environ.get("PORT", 5000))

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Flask App ────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

# ── Services ─────────────────────────────────────────────────────────────────
customs_reader = CustomsReader(CUSTOMS_PATH)
pitch_generator = PitchDeckGenerator(STORAGE_PATH)

# ── Database ─────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,
            company     TEXT,
            email       TEXT,
            phone       TEXT,
            title       TEXT,
            website     TEXT,
            industry    TEXT,
            customs_match TEXT,
            raw_ocr     TEXT,
            raw_enrichment TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS outreach (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id         INTEGER,
            email_sequence  TEXT,
            pitch_deck_path TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );
    """)
    conn.close()


# Init on module load
init_db()
os.makedirs(STORAGE_PATH, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


# ══════════════════════════════════════════════════════════════════════════════
# API ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": "exhibition-lead-sniper",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "gemini_configured": bool(gemini.GEMINI_API_KEY),
        "deepseek_configured": bool(deepseek.DEEPSEEK_API_KEY),
    })


@app.route("/api/backend-status")
def backend_status():
    """Frontend calls this to check if server is alive (always true now)."""
    return jsonify({"online": True, "status_code": 200, "url": "local (unified server)"})


# ── Upload & OCR ─────────────────────────────────────────────────────────────

@app.route("/api/upload-namecard", methods=["POST"])
def upload_namecard():
    """Accept business card image → OCR (Gemini) → Enrich → Save lead."""
    image_b64 = None
    filename = "namecard.jpg"

    if request.content_type and "multipart" in request.content_type:
        file = request.files.get("image")
        if not file:
            return jsonify({"error": "No image file provided"}), 400
        image_bytes = file.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        filename = file.filename or filename
    else:
        data = request.get_json(silent=True) or {}
        image_b64 = data.get("image_base64", "")
        filename = data.get("filename", filename)
        if not image_b64:
            return jsonify({"error": "No image data provided"}), 400

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/jpeg")

    # Step 1: OCR via Gemini
    try:
        card_data = gemini.extract_card_info(image_b64, mime_type)
    except Exception as e:
        logger.error("OCR failed: %s", e)
        return jsonify({"error": f"OCR failed: {str(e)}"}), 502

    # Step 2: Enrich company
    company = card_data.get("company", "")
    enrich_data = {}
    decision_makers = []
    if company or card_data.get("website"):
        try:
            enrich_data = enrichment.enrich_company(company, card_data.get("website"))
        except Exception as e:
            logger.warning("Enrichment failed (non-fatal): %s", e)
        try:
            decision_makers = enrichment.find_decision_makers(company, card_data.get("website"))
        except Exception as e:
            logger.warning("Decision maker search failed (non-fatal): %s", e)

    # Step 3: Match customs data
    customs_result = None
    if company:
        customs_result = customs_reader.match_company(company)

    # Step 4: Save to database
    lead_id = None
    try:
        conn = get_db()
        cursor = conn.execute(
            """INSERT INTO leads (name, company, email, phone, title, website, industry,
               customs_match, raw_ocr, raw_enrichment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                card_data.get("name", ""),
                company,
                card_data.get("email", ""),
                card_data.get("phone", ""),
                card_data.get("title", ""),
                card_data.get("website", ""),
                enrich_data.get("industry", ""),
                json.dumps(customs_result) if customs_result else None,
                json.dumps(card_data),
                json.dumps(enrich_data),
            ),
        )
        lead_id = cursor.lastrowid
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to save lead: %s", e)

    return jsonify({
        "success": True,
        "lead_id": lead_id,
        "card": card_data,
        "company_info": enrich_data,
        "decision_makers": decision_makers,
        "customs": customs_result,
    })


# ── Email Generation ─────────────────────────────────────────────────────────

@app.route("/api/generate-emails", methods=["POST"])
def generate_emails():
    """Generate 3-email cold outreach sequence via DeepSeek."""
    data = request.get_json(silent=True) or {}

    prospect = data.get("prospect", {})
    customs_history = data.get("customs_history", [])
    products = data.get("products", [])
    sender_name = data.get("sender_name")
    sender_company = data.get("sender_company")
    language = data.get("language", "en")

    try:
        emails = deepseek.generate_email_sequence(
            prospect=prospect,
            customs_history=customs_history,
            products=products,
            sender_name=sender_name,
            sender_company=sender_company,
            language=language,
        )
    except Exception as e:
        logger.error("Email generation failed: %s", e)
        return jsonify({"error": f"Email generation failed: {str(e)}"}), 502

    # Save outreach
    lead_id = data.get("lead_id")
    if lead_id:
        try:
            conn = get_db()
            conn.execute("INSERT INTO outreach (lead_id, email_sequence) VALUES (?, ?)",
                         (lead_id, json.dumps(emails)))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Failed to save outreach: %s", e)

    return jsonify({"success": True, "emails": emails})


# ── Pitch Deck ───────────────────────────────────────────────────────────────

@app.route("/api/generate-pitch-deck", methods=["POST"])
def generate_pitch_deck():
    """Generate a Morandi-themed pitch deck."""
    data = request.get_json(silent=True) or {}
    company_name = data.get("company", "Valued Customer")
    products = data.get("products", [])
    contact_info = data.get("contact_info", {})

    try:
        result = pitch_generator.generate(company_name, products, contact_info)
    except Exception as e:
        return jsonify({"error": f"Pitch deck generation failed: {str(e)}"}), 500

    return jsonify({"success": True, **result})


# ── Customs ──────────────────────────────────────────────────────────────────

@app.route("/api/customs-status")
def customs_status():
    return jsonify(customs_reader.status())


@app.route("/api/customs-reload", methods=["POST"])
def customs_reload():
    customs_reader.reload()
    return jsonify(customs_reader.status())


@app.route("/api/customs-match", methods=["POST"])
def customs_match():
    data = request.get_json(silent=True) or {}
    company = data.get("company", "").strip()
    if not company:
        return jsonify({"error": "company is required"}), 400
    return jsonify(customs_reader.match_company(company))


# ── Leads CRUD ───────────────────────────────────────────────────────────────

@app.route("/api/leads")
def list_leads():
    conn = get_db()
    rows = conn.execute("SELECT * FROM leads ORDER BY created_at DESC LIMIT 100").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/leads/<int:lead_id>")
def get_lead(lead_id):
    conn = get_db()
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if not lead:
        conn.close()
        return jsonify({"error": "Lead not found"}), 404
    outreach = conn.execute("SELECT * FROM outreach WHERE lead_id = ? ORDER BY created_at DESC", (lead_id,)).fetchall()
    conn.close()
    return jsonify({"lead": dict(lead), "outreach": [dict(o) for o in outreach]})


@app.route("/api/leads/<int:lead_id>", methods=["DELETE"])
def delete_lead(lead_id):
    conn = get_db()
    conn.execute("DELETE FROM outreach WHERE lead_id = ?", (lead_id,))
    conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ── File Download ────────────────────────────────────────────────────────────

@app.route("/api/download/<filename>")
def download_file(filename):
    safe_name = os.path.basename(filename)
    filepath = os.path.join(STORAGE_PATH, safe_name)
    if not os.path.isfile(filepath):
        return jsonify({"error": "File not found"}), 404
    return send_file(filepath, as_attachment=True, download_name=safe_name)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  Exhibition Lead Sniper v2.0")
    print(f"  http://0.0.0.0:{PORT}")
    print(f"  Gemini: {'✓' if gemini.GEMINI_API_KEY else '✗'}")
    print(f"  DeepSeek: {'✓' if deepseek.DEEPSEEK_API_KEY else '✗'}")
    print(f"  Customs: {customs_reader.status()['message']}")
    print(f"{'='*60}\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
