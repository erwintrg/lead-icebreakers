import pytest

from lead_icebreakers import language


@pytest.mark.parametrize("country, city, expected", [
    ("Germany", "Hamburg", ("de", "country")),
    ("Deutschland", "München", ("de", "country")),
    ("DE", "", ("de", "country")),
    ("Austria", "Wien", ("de", "country")),
    ("Österreich", "Graz", ("de", "country")),
    ("Liechtenstein", "Vaduz", ("de", "country")),
    ("Switzerland", "Zürich", ("de", "city")),
    ("CH", "8001 Zürich", ("de", "city")),
    ("Schweiz", "St. Gallen", ("de", "city")),
    ("Switzerland", "Genève", ("en", "city")),
    ("Suisse", "Lausanne", ("en", "city")),
    ("Switzerland", "Lugano", ("en", "city")),
    ("Switzerland", "Fribourg", ("ask", "model")),  # bilingual: left to the model
    ("Switzerland", "", ("ask", "model")),
    ("United Kingdom", "London", ("en", "country")),
    ("Netherlands", "Amsterdam", ("en", "country")),
    ("", "", ("en", "default")),
])
def test_detect_by_country_and_swiss_city(country, city, expected):
    assert language.detect({"country": country, "city": city}) == expected


def test_country_column_aliases():
    assert language.detect({"company_country": "Austria"}) == ("de", "country")
    assert language.detect({"Country": "Germany"}) == ("de", "country")


def test_hint_text_for_the_model():
    assert language.hint({"country": "Germany"}) == "de"
    assert language.hint({"country": "Spain"}) == "en"
    assert language.hint({"country": "Switzerland", "city": "Biel"}).startswith("decide")


def test_country_beats_the_model():
    assert language.resolve({"country": "Austria"}, "en") == ("de", "country")
    assert language.resolve({"country": "Ireland"}, "de") == ("en", "country")


def test_model_decides_only_unknown_swiss_cities():
    row = {"country": "Switzerland", "city": "Fribourg"}
    assert language.resolve(row, "de") == ("de", "model")
    assert language.resolve(row, "en") == ("en", "model")
    assert language.resolve(row, "fr") == ("en", "model")  # anything else falls back to English


def test_is_swiss():
    assert language.is_swiss({"country": "CH"})
    assert not language.is_swiss({"country": "Germany"})
