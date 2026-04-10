"""
tests/test_ollama.py
====================
Tests unitaires pour llm/ollama.py

On teste deux types de choses :
1. Tests sans Ollama (unitaires purs) - toujours rapides
2. Tests avec Ollama réel (intégration) - marqués @pytest.mark.integration
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm.ollama import Ollama, OllamaError


# ─────────────────────────────────────────────
# Tests unitaires (pas besoin d'Ollama)
# ─────────────────────────────────────────────

def test_ollama_default_values():
    """Les valeurs par défaut viennent bien de settings."""
    from config import settings
    ollama = Ollama()
    assert ollama.host == settings.OLLAMA_HOST
    assert ollama.model == settings.OLLAMA_MODEL


def test_ollama_custom_values():
    """On peut surcharger host et model."""
    ollama = Ollama(host="http://test:11434", model="llama3.2")
    assert ollama.host == "http://test:11434"
    assert ollama.model == "llama3.2"


def test_ollama_unavailable():
    """Si Ollama n'est pas sur ce port, is_available() retourne False."""
    ollama = Ollama(host="http://localhost:9999")
    assert ollama.is_available() is False


def test_ask_raises_when_unavailable():
    """ask() doit lever OllamaError si Ollama n'est pas disponible."""
    ollama = Ollama(host="http://localhost:9999")
    with pytest.raises(OllamaError):
        ollama.ask("test")


# ─────────────────────────────────────────────
# Tests d'intégration (nécessitent Ollama)
# ─────────────────────────────────────────────

@pytest.mark.integration
def test_ollama_is_available_real():
    """Ollama doit être accessible sur le port par défaut."""
    ollama = Ollama()
    assert ollama.is_available() is True


@pytest.mark.integration
def test_get_models_returns_list():
    """get_models() doit retourner une liste non vide."""
    ollama = Ollama()
    models = ollama.get_models()
    assert isinstance(models, list)
    assert len(models) > 0


@pytest.mark.integration
def test_ask_returns_string():
    """ask() doit retourner une string non vide."""
    ollama = Ollama()
    response = ollama.ask("Réponds juste 'ok'.")
    assert isinstance(response, str)
    assert len(response) > 0