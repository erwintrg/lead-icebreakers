"""Which template a lead gets: German for Germany, Austria, Liechtenstein and German-speaking
Swiss cities, English for everyone else. Code decides wherever it can; only a Swiss city that
is not in the lookup (bilingual Fribourg or Biel, a small town) is left to the model."""
from __future__ import annotations

import re
import unicodedata

from . import leads

GERMAN_COUNTRIES = {"germany", "deutschland", "de", "deu", "austria", "osterreich", "oesterreich",
                    "at", "aut", "liechtenstein", "li", "lie"}
SWISS = {"switzerland", "schweiz", "suisse", "svizzera", "svizra", "ch", "che"}

# Accents are folded before lookup, so "zürich" is stored as "zurich".
SWISS_GERMAN_CITIES = {
    "zurich", "zuerich", "basel", "bern", "berne", "luzern", "lucerne", "st. gallen", "st gallen",
    "sankt gallen", "winterthur", "zug", "baar", "cham", "aarau", "baden", "chur", "davos",
    "frauenfeld", "olten", "schaffhausen", "solothurn", "thun", "uster", "wil", "kreuzlingen",
    "rapperswil", "rapperswil-jona", "dubendorf", "duebendorf", "dietikon", "wadenswil",
    "waedenswil", "horgen", "thalwil", "adliswil", "kloten", "wallisellen", "wetzikon",
    "regensdorf", "emmen", "kriens", "koniz", "koeniz", "burgdorf", "langenthal", "allschwil",
    "riehen", "muttenz", "pratteln", "liestal", "herisau", "glarus", "schwyz", "altdorf",
    "sarnen", "stans", "appenzell", "brig", "visp",
}
SWISS_OTHER_CITIES = {  # French- and Italian-speaking
    "geneve", "geneva", "genf", "lausanne", "montreux", "vevey", "nyon", "morges", "renens",
    "pully", "gland", "rolle", "yverdon", "yverdon-les-bains", "neuchatel", "la chaux-de-fonds",
    "sion", "sierre", "martigny", "monthey", "delemont", "porrentruy", "bulle", "carouge",
    "meyrin", "vernier", "lancy", "onex", "lugano", "bellinzona", "locarno", "mendrisio",
    "chiasso", "ascona",
}

ASK = "ask"
ASK_HINT = "decide: de only if the company city is in German-speaking Switzerland, else en"


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _city(row: dict) -> str:
    city = _fold(leads.pick(row, leads.CITY_COLS)).split(",")[0]
    return re.sub(r"\d+", "", city).strip()  # "8001 Zürich" -> "zurich"


def detect(row: dict) -> tuple[str, str]:
    """(lang, source). lang is "de", "en" or "ask"; source says what decided it."""
    country = _fold(leads.pick(row, leads.COUNTRY_COLS))
    if not country:
        return "en", "default"
    if country in GERMAN_COUNTRIES:
        return "de", "country"
    if country in SWISS:
        city = _city(row)
        if city in SWISS_GERMAN_CITIES:
            return "de", "city"
        if city in SWISS_OTHER_CITIES:
            return "en", "city"
        return ASK, "model"
    return "en", "country"


def hint(row: dict) -> str:
    """The lang_hint the model gets for this row."""
    lang, _ = detect(row)
    return ASK_HINT if lang == ASK else lang


def resolve(row: dict, model_lang: str | None) -> tuple[str, str]:
    """Final language. A country or city decision always beats the model's answer."""
    lang, source = detect(row)
    if lang != ASK:
        return lang, source
    return (model_lang if model_lang in ("de", "en") else "en"), "model"


def is_swiss(row: dict) -> bool:
    return _fold(leads.pick(row, leads.COUNTRY_COLS)) in SWISS
