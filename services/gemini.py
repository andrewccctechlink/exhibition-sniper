"""Gemini API – OCR business cards + organize products for pitch deck."""

import json
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT = 120.0


def _build_url():
    return f"{GEMINI_BASE_URL}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"


def _parse_text(resp_json):
    candidates = resp_json.get("candidates", [])
    if not candidates:
        raise ValueError("No candidates in Gemini response")
    parts = candidates[0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def _extract_json(text):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def extract_card_info(image_base64: str, mime_type: str = "image/jpeg") -> dict:
    """OCR a business card image → {name, title, company, email, phone, website}."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not configured")

    prompt = (
        "You are an expert OCR assistant. Extract the following fields from this "
        "business card image and return ONLY a JSON object with these exact keys:\n"
        '  "name" (full name), "title" (job title), "company" (company name), '
        '  "email", "phone", "website"\n'
        "If a field is not present on the card, set its value to null.\n"
        "Do NOT include any explanation—just the JSON object."
    )

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": image_base64}},
            ]
        }],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }

    resp = httpx.post(_build_url(), json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    text = _parse_text(resp.json())
    data = _extract_json(text)

    return {
        "name": data.get("name"),
        "title": data.get("title"),
        "company": data.get("company"),
        "email": data.get("email"),
        "phone": data.get("phone"),
        "website": data.get("website"),
    }


def organize_products_for_pitch(products: list, prospect_company: str = None) -> dict:
    """Organize products into a structured pitch deck JSON."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not configured")

    prompt = (
        "You are a B2B sales strategist for kitchen appliances (EU/US markets).\n\n"
        f"Prospect company: {prospect_company or 'Unknown'}\n\n"
        "Organize these products into a pitch deck JSON. For each product:\n"
        '  - "name", "model", "category", "headline" (one-line sales hook),\n'
        '  - "key_selling_points" (3-5 bullets), "target_buyer_appeal",\n'
        '  - "certifications", "price"\n\n'
        "Also include: \"title\", \"prospect_company\", \"summary\" (2-3 sentences).\n"
        "Return ONLY JSON.\n\n"
        f"Products:\n{json.dumps(products, ensure_ascii=False, indent=2)}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4},
    }

    resp = httpx.post(_build_url(), json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    text = _parse_text(resp.json())
    return _extract_json(text)
