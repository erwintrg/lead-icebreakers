"""Contact data never reaches the model."""
import pytest

from lead_icebreakers import leads, prompts
from lead_icebreakers.pipeline import enrich_rows

from conftest import FakeBackend, make_rows


@pytest.mark.parametrize("name", [
    "email", "Email", "work_email", "E-Mail", "personalEmail", "email_combined", "phone", "phone_number",
    "Mobile", "Telefon", "tel", "fax", "LinkedIn", "linkedin_url", "LinkedIn Profile", "whatsapp",
    "street", "Address", "zip", "id", "lead_id", "apolloId",
])
def test_contact_columns_are_recognised(name):
    assert leads.is_contact_column(name)


@pytest.mark.parametrize("name", [
    "first_name", "last_name", "company_name", "company_domain", "website", "industry", "title",
    "city", "country", "hotel_name", "ideal_customer", "description",
])
def test_company_columns_are_not_contact_columns(name):
    assert not leads.is_contact_column(name)


@pytest.mark.parametrize("value, expected", [
    ("jane@example-consulting.example", True),
    ("Reach me at jane@example-consulting.example", True),
    ("+44 20 0000 0001", True),
    ("0044 20 0000 0001", True),
    ("030 1234 5678", True),
    ("https://linkedin.example/in/jane", True),
    ("https://www.linkedin.com/in/jane-example-0000", True),
    ("https://acmebox.com/", False),  # ends in "x.com/", not a profile link
    ("2015", False),
    ("25000000", False),
    ("1.000.000", False),
    ("Example Consulting", False),
])
def test_contact_looking_values(value, expected):
    assert leads.looks_like_contact_value(value) is expected


def test_payload_keeps_company_fields_and_drops_contact_data():
    row = {
        "first_name": "Jane", "last_name": "Example", "company_name": "Example Consulting",
        "company_domain": "example-consulting.example", "country": "Germany",
        "email": "jane@example-consulting.example", "phone": "+49 30 0000000",
        "linkedin_url": "https://linkedin.example/in/jane",
        "notes": "call jane@example-consulting.example",  # innocent column name, contact value
        "Icebreaker": "old line",
    }
    payload = prompts.lead_payload(7, row)
    assert payload == {
        "i": 7, "first_name": "Jane", "last_name": "Example", "company_name": "Example Consulting",
        "company_domain": "example-consulting.example", "country": "Germany", "lang_hint": "de",
    }


def test_long_values_are_capped():
    payload = prompts.lead_payload(0, {"first_name": "Jane", "description": "x" * 1000})
    assert len(payload["description"]) == prompts.MAX_VALUE_CHARS


def test_no_prompt_ever_contains_contact_data(quiet):
    rows = make_rows(9)
    backend = FakeBackend()
    enrich_rows(rows, backend, batch_size=4, log=quiet)
    assert backend.count("writer") == 3 and backend.count("reviewer") == 1
    for prompt in backend.prompts:
        for r in rows:
            assert r["email"] not in prompt
            assert r["linkedin_url"] not in prompt
            assert r["phone"] not in prompt
        for column in ("email", "phone", "linkedin_url"):
            assert f'"{column}"' not in prompt
    # the output keeps every original column
    assert all(r["email"].endswith(".example") and r["Icebreaker"].startswith("Hey ") for r in rows)
