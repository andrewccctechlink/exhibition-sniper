"""DeepSeek API – cold outreach email generation."""

import json
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
TIMEOUT = 120.0


def _extract_json(text):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def generate_email_sequence(
    prospect: dict,
    customs_history: list = None,
    products: list = None,
    sender_name: str = None,
    sender_company: str = None,
    language: str = "en",
) -> list:
    """Generate 3-email cold outreach sequence. Returns list of dicts."""
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY not configured")

    # Build customs summary
    customs_summary = ""
    if customs_history:
        lines = []
        for item in customs_history[:20]:
            parts = []
            for key in ("date", "product", "hs_code", "origin", "destination", "quantity", "value", "supplier"):
                if item.get(key):
                    parts.append(f"{key.title()}: {item[key]}")
            lines.append(" | ".join(parts))
        customs_summary = "\n".join(lines)

    product_summary = json.dumps(products[:15] if products else [], ensure_ascii=False, indent=2)

    system_prompt = (
        "You are an elite B2B sales copywriter specializing in kitchen appliance "
        "exports to European and American markets.\n\n"
        "Rules:\n"
        "- Write exactly 3 emails: Intro, Value Proposition, Follow-up\n"
        "- Reference the prospect's actual import history and product interests\n"
        "- Mention specific matching products from our list\n"
        "- Professional but warm tone\n"
        "- Each email under 200 words\n"
        "- Clear CTA in each email\n"
        f"- Language: {language}\n\n"
        "Return ONLY a JSON array with 3 objects:\n"
        '  {"sequence_number": 1|2|3, "subject": "...", "body": "...", "purpose": "intro|value_proposition|follow_up"}\n'
    )

    user_prompt = (
        f"## Prospect\n"
        f"Name: {prospect.get('name', 'N/A')}\n"
        f"Title: {prospect.get('title', 'N/A')}\n"
        f"Company: {prospect.get('company', 'N/A')}\n"
        f"Industry: {prospect.get('industry', 'N/A')}\n"
        f"Description: {prospect.get('company_description', 'N/A')}\n"
        f"Employees: {prospect.get('employee_count', 'N/A')}\n\n"
        f"## Their Import History\n{customs_summary or 'No data'}\n\n"
        f"## Our Products\n{product_summary}\n\n"
    )
    if sender_name:
        user_prompt += f"## Sender\nName: {sender_name}\n"
    if sender_company:
        user_prompt += f"Company: {sender_company}\n"
    user_prompt += "\nWrite the 3-email sequence now."

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
        "max_tokens": 4096,
    }

    resp = httpx.post(
        f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()

    text = resp.json()["choices"][0]["message"]["content"]
    parsed = _extract_json(text)

    if isinstance(parsed, dict):
        emails = parsed.get("emails", parsed.get("email_sequence", []))
        if not isinstance(emails, list):
            emails = [parsed]
    elif isinstance(parsed, list):
        emails = parsed
    else:
        emails = []

    return emails
