import pytest

from lead_icebreakers.template import Draft, check_slots, fill, load_languages, parse_line, render

UK = {"country": "United Kingdom"}
DE = {"country": "Germany"}
CH = {"country": "Switzerland", "city": "Zürich"}


def test_english_line_is_the_fixed_sentence():
    line = render(Draft("Mike", "Brightpath", "brand", "en"), UK)
    assert line == ("Hey Mike. Been thinking about Brightpath for a bit, "
                    "love what you're building and the bigger mission.")


def test_german_line_keeps_eszett():
    line = render(Draft("Max", "Hafenblick", "brand", "de"), DE)
    assert line.startswith("Hey Max. Hab Hafenblick schon eine Weile auf dem Schirm")
    assert "größere" in line


def test_swiss_line_uses_ss():
    line = render(Draft("Ursula", "Grünwerk Studio", "brand", "de"), CH)
    assert "grössere" in line and "ß" not in line
    assert "Grünwerk" in line  # only ß changes, umlauts stay


def test_slot_values_are_filled_once():
    # a value that looks like a slot must not be filled again
    assert fill("A {nick} B {company}", "{company}", "X") == "A {company} B X"


@pytest.mark.parametrize("row", [UK, DE, CH])
@pytest.mark.parametrize("draft", [
    Draft("Jane", "your consulting business", "generic", "en"),
    Draft("Lukas", "dein Online-Marketing-Business", "generic", "de"),
    Draft("Chris", "CloudRidge", "brand", "de"),
])
def test_parse_line_round_trip(draft, row):
    parsed = parse_line(render(draft, row))
    assert (parsed.nick, parsed.company, parsed.kind, parsed.lang) == (draft.nick, draft.company, draft.kind, draft.lang)


def test_parse_line_ignores_other_text():
    assert parse_line("Hi there, quick question") is None


@pytest.mark.parametrize("draft, problem", [
    (Draft("", "Acme", "brand", "en"), "empty"),
    (Draft("Max", "Hafenblick GmbH", "brand", "de"), "legal form"),
    (Draft("Anna", "Tradeloop BV", "brand", "en"), "legal form"),
    (Draft("Anna", "Tradeloop | Growth Partners", "brand", "en"), "tagline"),
    (Draft("Anna", "Tradeloop \u2014 Growth", "brand", "en"), "tagline"),
    (Draft("Jane", "your business", "generic", "en"), "too vague"),
    (Draft("Jane", "your company", "generic", "en"), "too vague"),
    (Draft("Jane", "your", "generic", "en"), "must start with"),  # a prefix alone is not a phrase
    (Draft("Jane", "consulting business", "generic", "en"), "must start with"),
    (Draft("Lukas", "your consulting business", "generic", "de"), "must start with"),  # English phrase, German line
    (Draft("Lukas", "deine Firma", "generic", "de"), "too vague"),
    (Draft("Mike", "Brightpath", "company", "en"), "kind"),
    (Draft("Mike", "Brightpath", "brand", "fr"), "language"),
    (Draft("Mike", "{company}", "brand", "en"), "brace"),
])
def test_bad_slots_are_rejected(draft, problem):
    assert problem in (check_slots(draft) or "")


@pytest.mark.parametrize("draft", [
    Draft("Mike", "Brightpath", "brand", "en"),
    Draft("Mike", "SAS", "brand", "en"),  # a brand that is only the letters
    Draft("José", "Northwind", "brand", "en"),
    Draft("Jane", "your consulting business", "generic", "en"),
    Draft("Daniel", "deine IT-Beratung", "generic", "de"),
])
def test_good_slots_pass(draft):
    assert check_slots(draft) is None


def test_template_needs_both_slots(tmp_path):
    bad = tmp_path / "templates.toml"
    bad.write_text('[en]\ntemplate = "Hey {nick}."\n[de]\ntemplate = "Hallo {nick}, {company}."\n', encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        load_languages(bad)
