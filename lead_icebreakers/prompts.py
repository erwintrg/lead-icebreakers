"""Everything the model sees: the per-row payload, the two system prompts and the JSON schemas."""
from __future__ import annotations

import json
import re
from functools import cache

from . import config, language, leads
from .template import languages

MAX_VALUE_CHARS = 300
WRITER_ASK = "Casual nick, company, kind and lang for these leads:"
REVIEW_ASK = "Check these finished lines:"


def lead_payload(i: int, row: dict) -> dict:
    """One row as the model sees it. Contact columns and contact-looking values are dropped."""
    out: dict = {"i": i}
    for key, value in row.items():
        if not key or key == leads.COLUMN or not isinstance(value, str) or not value.strip():
            continue
        if leads.is_contact_column(key) or leads.looks_like_contact_value(value):
            continue
        out[key] = value.strip()[:MAX_VALUE_CHARS]
    out["lang_hint"] = language.hint(row)
    return out


def writer_prompt(payload: list[dict]) -> str:
    return WRITER_ASK + "\n" + json.dumps(payload, ensure_ascii=False)


def reviewer_prompt(payload: list[dict]) -> str:
    return REVIEW_ASK + "\n" + json.dumps(payload, ensure_ascii=False)


def rows_in(prompt: str) -> list[dict]:
    """The JSON rows inside a prompt built above (the mock backend reads prompts this way)."""
    return json.loads(prompt.split("\n", 1)[1])


@cache
def rules() -> str:
    text = config.RULES_FILE.read_text(encoding="utf-8")
    return re.sub(r"<!--.*?-->\s*", "", text, flags=re.S).strip()


def _fixed_line() -> str:
    lines = "\n".join(f'{code.upper()}: "{lang.template}"' for code, lang in languages().items())
    return (
        f"The line is fixed:\n{lines}\n"
        "Only {nick} and {company} are filled in, so they must read naturally inside it, "
        "the way a person would casually talk to them."
    )


# Invented leads, shown to the writer as worked examples.
EXAMPLES = [
    ({"first_name": "Nicholas", "last_name": "Sample", "company_name": "Brightside Data Solutions LLC",
      "company_domain": "brightside.example", "lang_hint": "en"},
     {"nick": "Nick", "company": "Brightside", "kind": "brand", "lang": "en"}),
    ({"first_name": "MAXIMILIAN", "last_name": "Muster", "company_name": "Kontor Beratung GmbH & Co. KG",
      "company_domain": "kontor-beratung.example", "lang_hint": "de"},
     {"nick": "Max", "company": "Kontor", "kind": "brand", "lang": "de"}),
    ({"first_name": "Sarah", "last_name": "Sample", "company_name": "Digital Marketing",
      "company_domain": "dm-agency.example", "industry": "Marketing & Advertising", "lang_hint": "en"},
     {"nick": "Sarah", "company": "your digital marketing business", "kind": "generic", "lang": "en"}),
    ({"first_name": "Thomas", "last_name": "Beispiel", "company_name": "Beispiel Consulting GmbH",
      "company_domain": "beispiel-consulting.example", "lang_hint": "de"},
     {"nick": "Thomas", "company": "deine Beratung", "kind": "generic", "lang": "de"}),
]


@cache
def writer_system() -> str:
    examples = "\n".join(
        f"{json.dumps(lead, ensure_ascii=False)} -> {json.dumps(answer, ensure_ascii=False)}"
        for lead, answer in EXAMPLES
    )
    return f"""You prepare lead data for a cold email.

{_fixed_line()}

{rules()}

## lang

"de" or "en". Follow lang_hint. When it starts with "decide", pick "de" only if the company city is in German-speaking Switzerland.

Examples (invented leads):
{examples}

Return one entry per input row, keyed by its index i."""


@cache
def reviewer_system() -> str:
    return f"""You are the second reader on a cold-email list. Another writer already chose the nick and company words for each lead; you check them before anything is sent. For every row, read the finished line out loud as the recipient. Would a native speaker writing to this person phrase it exactly this way? Fix the row when it does not sound right.

{_fixed_line()}

{rules()}

Look hardest at: names that sound strange, negative, or like an ordinary word in the sentence; names longer than needed; domain spellings or odd capitalisation; a second word kept without being part of the identity; companies named after the lead; generic phrases that are vague, clunky or ungrammatical (especially the German possessive). Leave rows that already sound natural exactly as they are.

Return every row with its final nick, company and kind, and reason = a few words on what you changed, or "" when unchanged."""


def _schema(fields: dict) -> dict:
    return {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"i": {"type": "integer"}, **fields},
                    "required": ["i", *fields],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["rows"],
        "additionalProperties": False,
    }


_NICK_COMPANY_KIND = {
    "nick": {"type": "string"},
    "company": {"type": "string"},
    "kind": {"type": "string", "enum": ["brand", "generic"]},
}
WRITER_SCHEMA = _schema({**_NICK_COMPANY_KIND, "lang": {"type": "string", "enum": ["de", "en"]}})
REVIEW_SCHEMA = _schema({**_NICK_COMPANY_KIND, "reason": {"type": "string"}})


def is_review(schema: dict) -> bool:
    return "reason" in schema["properties"]["rows"]["items"]["properties"]
