"""Contracts for the language selector shared by the current landing pages."""

from pathlib import Path


LANDING = Path("landing")


def test_every_current_language_button_has_a_live_label():
    for page_name in ("index.html", "news.html"):
        page = (LANDING / page_name).read_text(encoding="utf-8")
        assert page.count('data-action="toggleLang"') == 1
        assert page.count("data-lang-label") == 1


def test_language_change_updates_the_visible_button_label():
    script = (LANDING / "app.v2.js").read_text(encoding="utf-8")
    assert "lbl.textContent = cur.toUpperCase()" in script
    assert "window.addEventListener('flx:langchange'" in script
    assert "markLang();" in script
