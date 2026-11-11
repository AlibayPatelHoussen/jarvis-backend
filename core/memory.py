"""
core/memory.py
==============
Système de mémoire de Jarvis.

Deux niveaux :
- ShortTermMemory : historique de la conversation en cours.
  Stocké en RAM. Perdu quand Jarvis s'arrête.
  Utilisé pour donner le contexte au LLM.

- LongTermMemory : faits importants sur l'utilisateur.
  Stocké en SQLite. Persiste entre les sessions.
  Exemple : prénom, ville, préférences...
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from config import settings


# ─────────────────────────────────────────────
# MÉMOIRE COURT TERME
# ─────────────────────────────────────────────

class ShortTermMemory:
    """
    Historique de la conversation en cours.

    Stocke les messages sous forme de liste :
    [
        {"role": "user",      "content": "Bonjour"},
        {"role": "assistant", "content": "Bonjour !"},
        ...
    ]

    C'est exactement le format attendu par Ollama.
    """

    def __init__(self, max_messages: int = 20):
        """
        Args:
            max_messages : Nombre maximum de messages à garder.
                           Au-delà, les plus anciens sont supprimés.
                           Pourquoi ? Pour ne pas dépasser la fenêtre
                           contextuelle du modèle IA.
        """
        self.max_messages = max_messages
        self._messages: list[dict] = []

    def add(self, role: str, content: str) -> None:
        """
        Ajoute un message à l'historique.

        Args:
            role    : "user" ou "assistant"
            content : Le texte du message
        """
        self._messages.append({
            "role": role,
            "content": content
        })

        # Si on dépasse la limite, supprimer les plus anciens.
        # Le Brain ajoute toujours un message user puis un message
        # assistant : avec une limite paire, l'historique commence
        # donc toujours par un message user.
        if len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages:]

    def get_history(self) -> list[dict]:
        """
        Retourne l'historique complet.

        Returns:
            Liste de dicts {"role": ..., "content": ...}
        """
        return self._messages.copy()

    def clear(self) -> None:
        """Efface tout l'historique."""
        self._messages = []

    def count(self) -> int:
        """Retourne le nombre de messages dans l'historique."""
        return len(self._messages)


# ─────────────────────────────────────────────
# MÉMOIRE LONG TERME
# ─────────────────────────────────────────────

class LongTermMemory:
    """
    Mémoire persistante stockée en SQLite.

    Stocke des faits sous forme clé → valeur :
        "prenom"     → "Houssen"
        "ville"      → "Montréal"
        "profession" → "développeur"

    Chaque fait a une date de création et de
    dernière mise à jour.
    """

    def __init__(self, db_path: Path = None):
        """
        Args:
            db_path : Chemin vers le fichier SQLite.
                      Défaut : data/memory.db
        """
        self.db_path = db_path or settings.MEMORY_DB
        self._init_db()

    def _init_db(self) -> None:
        """
        Crée la base de données et la table si elles
        n'existent pas encore.

        Pourquoi ici et pas dans un fichier séparé ?
        La mémoire est responsable de sa propre structure.
        """
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """
        Ouvre une connexion SQLite, valide la transaction puis la ferme.

        Attention : "with sqlite3.connect(...)" seul valide la
        transaction mais NE ferme PAS la connexion (fuite de
        connexions, fichier verrouillé sous Windows).
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def save(self, key: str, value: str) -> None:
        """
        Sauvegarde un fait.
        Si la clé existe déjà, met à jour la valeur.

        Args:
            key   : Identifiant du fait (ex: "prenom")
            value : Valeur du fait (ex: "Houssen")
        """
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO facts (key, value, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value      = excluded.value,
                    updated_at = excluded.updated_at
            """, (key, value, now, now))

    def get(self, key: str) -> Optional[str]:
        """
        Récupère un fait par sa clé.

        Args:
            key : La clé du fait

        Returns:
            La valeur ou None si la clé n'existe pas
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT value FROM facts WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_all(self) -> dict[str, str]:
        """
        Retourne tous les faits sous forme de dictionnaire.

        Returns:
            {"prenom": "Houssen", "ville": "Montréal", ...}
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT key, value FROM facts ORDER BY created_at, rowid"
            )
            return {row[0]: row[1] for row in cursor.fetchall()}

    def delete(self, key: str) -> bool:
        """
        Supprime un fait.

        Returns:
            True si supprimé, False si clé inexistante
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM facts WHERE key = ?",
                (key,)
            )
            return cursor.rowcount > 0

    def count(self) -> int:
        """Retourne le nombre de faits stockés."""
        with self._connect() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM facts")
            return cursor.fetchone()[0]
