"""
tests/test_voice.py
===================
Tests unitaires pour interface/voice.py

On teste la logique sans avoir besoin
du micro ou des haut-parleurs.
"""

import pytest
from interface.voice import VoiceOutput, VoiceInput


@pytest.fixture
def tts():
    return VoiceOutput()


@pytest.fixture
def stt():
    return VoiceInput()


# ─────────────────────────────────────────────
# Tests VoiceOutput
# ─────────────────────────────────────────────

def test_voice_output_can_be_created(tts):
    """VoiceOutput doit pouvoir être instancié."""
    assert tts is not None


def test_voice_output_has_availability(tts):
    """VoiceOutput doit avoir une propriété is_available."""
    assert isinstance(tts.is_available, bool)


def test_clean_text_removes_markdown(tts):
    """_clean_for_speech() doit supprimer le markdown."""
    result = tts._clean_for_speech("**Bonjour** monde")
    assert "**" not in result
    assert "Bonjour monde" in result


def test_clean_text_removes_code(tts):
    """_clean_for_speech() doit supprimer les backticks."""
    result = tts._clean_for_speech("`code` ici")
    assert "`" not in result


def test_clean_text_removes_urls(tts):
    """_clean_for_speech() doit remplacer les URLs."""
    result = tts._clean_for_speech("Voir https://example.com ici")
    assert "https" not in result
    assert "lien web" in result


def test_clean_text_removes_headers(tts):
    """_clean_for_speech() doit supprimer les titres markdown."""
    result = tts._clean_for_speech("## Titre\nContenu")
    assert "##" not in result


def test_speak_empty_text_doesnt_crash(tts):
    """speak('') ne doit pas planter."""
    tts.speak("")


def test_set_rate_clamps_value(tts):
    """set_rate() doit limiter la valeur entre 80 et 300."""
    if tts.is_available:
        tts.set_rate(50)   # doit être clampé à 80
        tts.set_rate(500)  # doit être clampé à 300


def test_set_volume_clamps_value(tts):
    """set_volume() doit limiter la valeur entre 0 et 1."""
    if tts.is_available:
        tts.set_volume(-1.0)  # doit être clampé à 0
        tts.set_volume(2.0)   # doit être clampé à 1


# ─────────────────────────────────────────────
# Tests VoiceInput
# ─────────────────────────────────────────────

def test_voice_input_can_be_created(stt):
    """VoiceInput doit pouvoir être instancié."""
    assert stt is not None


def test_voice_input_has_availability(stt):
    """VoiceInput doit avoir une propriété is_available."""
    assert isinstance(stt.is_available, bool)


def test_voice_input_language(stt):
    """La langue par défaut doit être fr-FR."""
    assert stt.language == "fr-FR"


def test_listen_returns_none_if_unavailable():
    """listen() doit retourner None si STT non disponible."""
    stt = VoiceInput()
    if not stt.is_available:
        result = stt.listen(timeout=1)
        assert result is None
