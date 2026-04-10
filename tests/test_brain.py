"""
tests/test_brain.py
===================
Tests unitaires pour core/brain.py
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.brain import Brain


# ─────────────────────────────────────────────
# Tests unitaires (pas besoin d'Ollama)
# ─────────────────────────────────────────────

def test_brain_can_be_created():
    """Le Brain doit pouvoir être instancié."""
    brain = Brain()
    assert brain is not None


def test_brain_has_llm():
    """Le Brain doit avoir un client LLM."""
    brain = Brain()
    assert brain.llm is not None


def test_process_empty_message():
    """Un message vide doit retourner une string vide."""
    brain = Brain()
    response = brain.process("")
    assert response == ""


def test_process_whitespace_message():
    """Un message avec juste des espaces doit retourner vide."""
    brain = Brain()
    response = brain.process("   ")
    assert response == ""


# ─────────────────────────────────────────────
# Tests d'intégration (nécessitent Ollama)
# ─────────────────────────────────────────────

@pytest.mark.integration
def test_brain_is_ready():
    """Le Brain doit être opérationnel si Ollama tourne."""
    brain = Brain()
    assert brain.is_ready() is True


@pytest.mark.integration
def test_process_returns_string():
    """process() doit retourner une string non vide."""
    brain = Brain()
    response = brain.process("Réponds juste 'ok'.")
    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.integration
def test_process_responds_in_french():
    """Jarvis doit répondre en français."""
    brain = Brain()
    response = brain.process("Quelle est ta langue principale ?")
    # Vérifier que la réponse contient des mots français courants
    french_words = ["français", "france", "je", "est", "pour", "dans"]
    response_lower = response.lower()
    assert any(word in response_lower for word in french_words)