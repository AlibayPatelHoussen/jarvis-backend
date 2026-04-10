"""
tests/test_settings.py
======================
Tests unitaires pour config/settings.py

On vérifie que :
- Les valeurs par défaut sont correctes
- Les dossiers sont créés automatiquement
- La lecture du .env fonctionne
"""

import os

import config.settings as settings


def test_default_language():
    """La langue par défaut doit être 'fr'."""
    # Si pas de .env, la valeur par défaut est 'fr'
    if "JARVIS_LANGUAGE" not in os.environ:
        assert settings.LANGUAGE == "fr"


def test_default_ollama_host():
    """L'host Ollama par défaut doit pointer sur localhost."""
    if "OLLAMA_HOST" not in os.environ:
        assert settings.OLLAMA_HOST == "http://localhost:11434"


def test_default_ollama_model():
    """Le modèle par défaut doit être mistral."""
    if "OLLAMA_MODEL" not in os.environ:
        assert settings.OLLAMA_MODEL == "mistral"


def test_data_dir_exists():
    """Le dossier data/ doit être créé automatiquement."""
    assert settings.DATA_DIR.exists()
    assert settings.DATA_DIR.is_dir()


def test_logs_dir_exists():
    """Le dossier logs/ doit être créé automatiquement."""
    assert settings.LOGS_DIR.exists()
    assert settings.LOGS_DIR.is_dir()


def test_root_is_correct():
    """ROOT doit pointer vers la racine du projet."""
    assert (settings.ROOT / "config").exists()
    assert (settings.ROOT / "core").exists()
