"""Lead enrichment – Hunter.io, Snov.io, Google Maps, website scraping."""

import logging
import os
import re
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "")
SNOV_USER_ID = os.environ.get("SNOV_USER_ID", "")
SNOV_SECRET = os.environ.get("SNOV_SECRET", "")
GOOGLE_MAPS_KEY = os.environ.get("GOOGLE_MAPS_KEY", "")
TIMEOUT = 30.0


def _extract_domain(website):
    if not website:
        return None
    website = website.strip()
    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"
    parsed = urlparse(website)
    domain = parsed.hostname or parsed.path.split("/")[0]
    if domain:
        domain = domain.lower().removeprefix("www.")
    return domain or None


def _google_maps_enrich(company_name):
    """Search Google Maps Places API for company info."""
    if not GOOGLE_MAPS_KEY:
        return {}
    try:
        resp = httpx.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": GOOGLE_MAPS_KEY,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.internationalPhoneNumber,places.websiteUri,places.rating,places.types",
            },
            json={"textQuery": company_name, "maxResultCount": 1},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return {}
        places = resp.json().get("places", [])
        if not places:
            return {}
        p = places[0]
        return {
            "phone": p.get("internationalPhoneNumber", ""),
            "address": p.get("formattedAddress", ""),
            "website": p.get("websiteUri", ""),
            "rating": p.get("rating"),
            "types": p.get("types", []),
        }
    except Exception as e:
        logger.warning("Google Maps error: %s", e)
        return {}


def _hunter_search(domain):
    """Find emails via Hunter.io domain search."""
    if not HUNTER_API_KEY:
        return []
    try:
        resp = httpx.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": HUNTER_API_KEY, "limit": 5},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        emails = resp.json().get("data", {}).get("emails", [])
        results = []
        for e in emails:
            results.append({
                "name": f"{e.get('first_name', '')} {e.get('last_name', '')}".strip() or None,
                "title": e.get("position") or e.get("seniority"),
                "email": e.get("value"),
                "linkedin_url": e.get("linkedin"),
                "phone": e.get("phone_number"),
                "source": "hunter",
            })
        return results
    except Exception as e:
        logger.warning("Hunter error: %s", e)
        return []


def _snov_search(domain):
    """Find emails via Snov.io domain search."""
    if not SNOV_USER_ID or not SNOV_SECRET:
        return []
    try:
        # Get token
        token_resp = httpx.post(
            "https://api.snov.io/v1/oauth/access_token",
            json={"grant_type": "client_credentials", "client_id": SNOV_USER_ID, "client_secret": SNOV_SECRET},
            timeout=TIMEOUT,
        )
        if token_resp.status_code != 200:
            return []
        token = token_resp.json().get("access_token")
        if not token:
            return []

        resp = httpx.post(
            "https://api.snov.io/v2/domain-emails-with-info",
            headers={"Authorization": f"Bearer {token}"},
            json={"domain": domain, "limit": 5},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        emails = resp.json().get("emails", resp.json().get("data", []))
        results = []
        if isinstance(emails, list):
            for e in emails:
                results.append({
                    "name": f"{e.get('firstName', '')} {e.get('lastName', '')}".strip() or None,
                    "title": e.get("position"),
                    "email": e.get("email"),
                    "phone": e.get("phone"),
                    "linkedin_url": None,
                    "source": "snov",
                })
        return results
    except Exception as e:
        logger.warning("Snov error: %s", e)
        return []


def _scrape_website_emails(domain):
    """Scrape company website for email addresses (free)."""
    found = set()
    pages = [f"https://{domain}", f"https://{domain}/contact", f"https://{domain}/about"]
    for url in pages:
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=5.0,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; B2BResearch/1.0)"})
            if resp.status_code != 200:
                continue
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', resp.text)
            for e in emails:
                lower = e.lower()
                if not lower.endswith(('.png', '.jpg', '.gif', '.svg', '.css', '.js')):
                    found.add(lower)
        except Exception:
            continue
    return list(found)


# ── Public API ───────────────────────────────────────────────────────────────

def enrich_company(company_name=None, website=None):
    """Enrich company info. Returns dict with industry, phone, address, etc."""
    domain = _extract_domain(website)
    result = {
        "industry": None,
        "employee_count": None,
        "description": None,
        "phone": None,
        "address": None,
        "website": website,
        "emails_scraped": [],
    }

    if company_name:
        maps_data = _google_maps_enrich(company_name)
        if maps_data:
            result["phone"] = maps_data.get("phone")
            result["address"] = maps_data.get("address")
            result["website"] = maps_data.get("website") or website
            types = maps_data.get("types", [])
            if types:
                result["industry"] = ", ".join(t.replace("_", " ").title() for t in types[:3])

    if domain:
        result["emails_scraped"] = _scrape_website_emails(domain)

    return result


def find_decision_makers(company_name=None, company_domain=None, limit=5):
    """Find decision makers using Hunter.io + Snov.io."""
    domain = _extract_domain(company_domain) if company_domain else None
    if not domain and not company_name:
        return []

    all_contacts = []
    seen_emails = set()

    if domain:
        for contact in _hunter_search(domain):
            email = contact.get("email", "")
            if email and email not in seen_emails:
                seen_emails.add(email)
                all_contacts.append(contact)

        if len(all_contacts) < limit:
            for contact in _snov_search(domain):
                email = contact.get("email", "")
                if email and email not in seen_emails:
                    seen_emails.add(email)
                    all_contacts.append(contact)

    return all_contacts[:limit]
