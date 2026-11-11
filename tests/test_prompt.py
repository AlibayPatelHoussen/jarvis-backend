"""
tests/test_prompt.py
====================
Tests unitaires pour core/prompt.py
"""

from datetime import datetime

from config import settings
from core.prompt import build_system_prompt, format_date_fr


def test_format_date_fr():
    now = datetime(2026, 11, 11, 14, 5)
    assert format_date_fr(now) == "mercredi 11 novembre 2026, 14 h 05"


def test_prompt_contains_date_and_iso():
    prompt = build_system_prompt(now=datetime(2026, 1, 3, 9, 0))
    assert "samedi 3 janvier 2026" in prompt
    assert "2026-01-03T09:00" in prompt


def test_prompt_contains_facts_and_sections():
    prompt = build_system_prompt(
        known_facts=["j'habite à Montréal"],
        extra_sections=["Outils : calculer"],
    )
    assert "- j'habite à Montréal" in prompt
    assert "Outils : calculer" in prompt


def test_prompt_language(monkeypatch):
    monkeypatch.setattr(settings, "LANGUAGE", "en")
    assert "English" in build_system_prompt()
    monkeypatch.setattr(settings, "LANGUAGE", "fr")
    assert "français" in build_system_prompt()
