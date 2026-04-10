"""
config/settings.py
==================
Gestionnaire de configuration de Jarvis.

Responsabilité unique : charger et exposer la configuration.
Le reste du code importe depuis ce fichier, jamais depuis le JSON directement.
"""

import os
from pathlib import Path

# Racine du projet (le dossier jarvis-backend/)
ROOT = Path(__file__).parent.parent


def _load_env() -> None:
    """
    Lit le fichier .env et charge les variables dans os.environ.

    Pourquoi manuellement ?
    Pour ne pas avoir de dépendance externe (python-dotenv)
    au tout début du projet. On l'ajoutera plus tard.
    """
    env_file = ROOT / ".env"
    if not env_file.exists():
        return

    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Ignorer les commentaires et lignes vides
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Ne pas écraser si déjà défini dans l'environnement réel
            if key and value and key not in os.environ:
                os.environ[key] = value


# Charger .env au démarrage de ce module
_load_env()


# ─────────────────────────────────────────────
# CONFIGURATION — valeurs lues depuis .env
# avec des valeurs par défaut raisonnables
# ─────────────────────────────────────────────

# Utilisateur
USER_NAME: str = os.environ.get("JARVIS_USER_NAME", "Utilisateur")
LANGUAGE: str = os.environ.get("JARVIS_LANGUAGE", "fr")

# Ollama (LLM local)
OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "mistral")

# Anthropic (LLM cloud, optionnel)
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")

# Chemins des fichiers de données
DATA_DIR: Path = ROOT / "data"
MEMORY_DB: Path = DATA_DIR / "memory.db"
LOGS_DIR: Path = ROOT / "logs"

# Créer les dossiers si ils n'existent pas
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
