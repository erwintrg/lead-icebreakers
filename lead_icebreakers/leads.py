"""Lead rows: which column holds what, and what must never reach the model."""
from __future__ import annotations

import re

COLUMN = "Icebreaker"

FIRST_NAME_COLS = ("first_name", "firstName", "First Name", "first name", "Vorname")
COMPANY_COLS = ("company_name", "companyName", "Company Name", "Company", "company", "organization_name", "Firma")
DOMAIN_COLS = ("company_domain", "domain", "Domain", "website", "Website", "company_website")
COUNTRY_COLS = ("company_country", "country", "Country", "Land")
CITY_COLS = ("company_city", "city", "City", "Stadt", "Ort")

# Contact details add nothing to a first name and a company name, so they never go to the
# model. Unambiguous markers match anywhere in the column name ("work_email", "LinkedIn
# Profile"); short ones only as a whole word ("tel", not "hotel").
_CONTACT_PARTS = ("mail", "phone", "mobile", "linkedin", "whatsapp", "twitter", "telegram",
                  "fax", "street", "address", "postcode", "zipcode")
_CONTACT_WORDS = {"tel", "telefon", "handy", "cell", "zip", "plz", "id", "uuid"}
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PROFILE_URL = re.compile(r"(?<![\w-])(linkedin\.|twitter\.com|x\.com/|wa\.me/)", re.I)


def pick(row: dict, cols: tuple[str, ...]) -> str:
    """The first non-empty value among the column aliases."""
    for c in cols:
        value = row.get(c)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def first_name(row: dict) -> str:
    return pick(row, FIRST_NAME_COLS)


def company(row: dict) -> str:
    return pick(row, COMPANY_COLS)


def _words(name: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)  # camelCase -> camel Case
    return [w for w in re.split(r"[^a-z0-9]+", spaced.lower()) if w]


def is_contact_column(name: str) -> bool:
    flat = re.sub(r"[^a-z0-9]", "", name.lower())
    return any(p in flat for p in _CONTACT_PARTS) or any(w in _CONTACT_WORDS for w in _words(name))


def _looks_like_phone(value: str) -> bool:
    if not re.fullmatch(r"\+?[\d\s()/.-]+", value):
        return False
    digits = sum(c.isdigit() for c in value)
    return digits >= 7 and (value.startswith(("+", "00")) or re.search(r"\d[\s()/-]+\d", value) is not None)


def looks_like_contact_value(value: str) -> bool:
    """Second line of defence: contact data sitting in a column with an innocent name."""
    value = value.strip()
    return bool(_EMAIL.search(value) or _PROFILE_URL.search(value) or _looks_like_phone(value))
