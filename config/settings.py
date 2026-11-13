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
# Lire les réponses à voix haute (si pyttsx3 est disponible)
VOICE_ENABLED: bool = os.environ.get("JARVIS_VOICE", "on").lower() not in (
    "off", "0", "non", "false"
)

# Ollama (LLM local)
OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "mistral")
try:
    OLLAMA_NUM_CTX: int = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))
except ValueError:
    OLLAMA_NUM_CTX = 4096

# Laisser le modèle utiliser des outils (nécessite un modèle compatible)
TOOLS_ENABLED: bool = os.environ.get("JARVIS_TOOLS", "on").lower() not in (
    "off", "0", "non", "false"
)

# Environnement local (étape 4)
# Dossier où Jarvis peut lire et écrire des fichiers (défaut : dossier personnel)
WORKSPACE: Path = Path(os.environ.get("JARVIS_WORKSPACE") or Path.home()).expanduser()
# Autoriser l'outil "executer_commande" (chaque commande reste à confirmer)
ALLOW_COMMANDS: bool = os.environ.get("JARVIS_ALLOW_COMMANDS", "on").lower() not in (
    "off", "0", "non", "false"
)
try:
    COMMAND_TIMEOUT: int = int(os.environ.get("JARVIS_COMMAND_TIMEOUT", "30"))
except ValueError:
    COMMAND_TIMEOUT = 30

# Mode serveur (python start.py --server)
# Clé d'accès principale, obligatoire pour l'API
API_KEY: str = os.environ.get("JARVIS_API_KEY", "")
# 127.0.0.1 = accessible seulement depuis la machine (via un tunnel HTTPS)
SERVER_HOST: str = os.environ.get("JARVIS_HOST", "127.0.0.1")
try:
    SERVER_PORT: int = int(os.environ.get("JARVIS_PORT", "8765"))
except ValueError:
    SERVER_PORT = 8765
try:
    CONFIRM_TIMEOUT: int = int(os.environ.get("JARVIS_CONFIRM_TIMEOUT", "120"))
except ValueError:
    CONFIRM_TIMEOUT = 120

# Interfaces web autorisées à appeler l'API depuis le navigateur (CORS),
# séparées par des virgules, ex. https://jarvis-app.mondomaine.com
CORS_ORIGINS: list = [o.strip() for o in os.environ.get("JARVIS_CORS_ORIGINS", "").split(",")
                      if o.strip()]

# Application hôte qui fournit des outils à Jarvis (ex. Nexus) :
# adresse de ses outils et secret partagé (JARVIS_TOOLS_SECRET côté Nexus)
HOST_TOOLS_URL: str = os.environ.get("JARVIS_HOST_TOOLS_URL", "").strip()
HOST_SECRET: str = os.environ.get("JARVIS_HOST_SECRET", "").strip()

# Notifications push : contact transmis aux services de push des navigateurs
# (Apple, Google, Mozilla) avec chaque envoi — un e-mail « mailto:… » ou une URL https
PUSH_CONTACT: str = os.environ.get("JARVIS_PUSH_CONTACT", "mailto:jarvis@example.com")

# Anthropic (LLM cloud, optionnel)
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")

# Chemins des fichiers de données
# Dossier des données (mémoire, tâches...) — modifiable avec JARVIS_DATA_DIR
DATA_DIR: Path = Path(os.environ.get("JARVIS_DATA_DIR") or ROOT / "data")
MEMORY_DB: Path = DATA_DIR / "memory.db"
LOGS_DIR: Path = ROOT / "logs"

# Créer les dossiers si ils n'existent pas
DATA_DIR.mkdir(parents=True, exist_ok=True)
try:
    LOGS_DIR.mkdir(exist_ok=True)
except OSError:  # dossier du code en lecture seule (installation serveur)
    pass
