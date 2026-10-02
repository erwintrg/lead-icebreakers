"""The fixed sentence: load it, fill its two slots, read a finished line back, and check slot
values before they are allowed into a line."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from . import config, language

SLOT = re.compile(r"\{(nick|company)\}")
KINDS = ("brand", "generic")
# A legal form left after a brand name ("Acme GmbH"). A brand that is only the letters
# ("SAS") is fine, so the form must follow another word.
LEGAL_FORM = re.compile(
    r"[\s,](gmbh|ag|ug|kg|ohg|gbr|e\.\s?k|llc|ltd|plc|inc|corp|b\.?v|s\.?l|s\.?r\.?l|sas|sarl|a/s|ab|aps|oy)\.?$",
    re.I,
)
TAGLINE = re.compile("[|\u2013\u2014]")  # pipe, en dash, em dash
MAX_NICK, MAX_COMPANY = 40, 80


@dataclass(frozen=True)
class Language:
    code: str
    template: str
    generic_prefixes: tuple[str, ...]
    too_vague: frozenset[str]


@dataclass
class Draft:
    """What the model decided for one row: the two slot values and the line's language."""

    nick: str
    company: str
    kind: str  # "brand" or "generic"
    lang: str  # "en" or "de"
    lang_source: str = ""  # what decided the language: country, city, model, default, parsed

    @property
    def label(self) -> str:
        return f"{self.nick} / {self.company}"


@dataclass(order=True)
class Change:
    row: int  # spreadsheet row number (the header is row 1)
    stage: str  # "review" or "override"
    before: str
    after: str
    reason: str


def load_languages(path: Path = config.TEMPLATES_FILE) -> dict[str, Language]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    langs = {}
    for code, spec in data.items():
        template = spec["template"]
        if sorted(SLOT.findall(template)) != ["company", "nick"]:
            raise ValueError(f"{path}: [{code}] template needs exactly one {{nick}} and one {{company}}")
        langs[code] = Language(
            code=code,
            template=template,
            generic_prefixes=tuple(p.lower() for p in spec.get("generic_prefixes", [])),
            too_vague=frozenset(v.lower() for v in spec.get("too_vague", [])),
        )
    if missing := {"en", "de"} - set(langs):
        raise ValueError(f"{path}: missing template(s) for {', '.join(sorted(missing))}")
    return langs


@cache
def languages() -> dict[str, Language]:
    return load_languages()


def fill(template: str, nick: str, company: str) -> str:
    """Single pass, so a slot value can never be read as another slot."""
    values = {"nick": nick, "company": company}
    return SLOT.sub(lambda m: values[m.group(1)], template)


def render(draft: Draft, row: dict, langs: dict[str, Language] | None = None) -> str:
    langs = langs or languages()
    text = fill(langs[draft.lang].template, draft.nick.strip(), draft.company.strip())
    if language.is_swiss(row):
        text = text.replace("ß", "ss")  # Swiss German has no ß
    return text


def _starts_generic(company: str, lang: Language) -> bool:
    words = company.split()
    return len(words) >= 2 and words[0].lower() in lang.generic_prefixes


def parse_line(line: str, langs: dict[str, Language] | None = None) -> Draft | None:
    """Read nick, company and language back out of a finished line (Swiss "ss" included)."""
    langs = langs or languages()
    line = line.strip()
    for code, lang in langs.items():
        pattern, pos = "", 0
        for m in SLOT.finditer(lang.template):
            pattern += _literal(lang.template[pos:m.start()]) + f"(?P<{m.group(1)}>.+?)"
            pos = m.end()
        pattern += _literal(lang.template[pos:])
        if found := re.fullmatch(pattern, line):
            company = found["company"]
            kind = "generic" if _starts_generic(company, lang) else "brand"
            return Draft(found["nick"], company, kind, code, "parsed")
    return None


def _literal(text: str) -> str:
    return re.escape(text).replace("ß", "(?:ß|ss)")


def check_slots(draft: Draft, langs: dict[str, Language] | None = None) -> str | None:
    """Why this draft must not go into a line, or None when it is fine."""
    langs = langs or languages()
    nick, company = draft.nick.strip(), draft.company.strip()
    if not nick or not company:
        return "empty nick or company"
    if draft.lang not in langs:
        return f"unknown language {draft.lang!r}"
    if draft.kind not in KINDS:
        return f"kind must be brand or generic, not {draft.kind!r}"
    if re.search(r"[{}\n\r]", nick + company):
        return "brace or line break in a slot"
    if TAGLINE.search(nick + company):
        return "tagline or long dash left in a name"
    if len(nick) > MAX_NICK or len(company) > MAX_COMPANY:
        return "slot value too long"
    lang = langs[draft.lang]
    if draft.kind == "generic":
        if not _starts_generic(company, lang):
            return f"generic phrase {company!r} must start with {' / '.join(lang.generic_prefixes)}"
        if company.lower() in lang.too_vague:
            return f"generic phrase {company!r} is too vague"
    elif LEGAL_FORM.search(company):
        return f"legal form left in {company!r}"
    return None
