"""
core/clients.py
===============
Clés d'accès par application.

Chaque application qui parle à Jarvis (Nexus, le téléphone, un autre
logiciel) a sa propre clé : on peut la retirer sans toucher aux autres,
et limiter ce qu'elle peut faire.

    python start.py cles ajouter telephone
    python start.py cles ajouter nexus --role admin --confiance
    python start.py cles liste
    python start.py cles supprimer telephone

Une clé a :
- un rôle maximal : "admin" (tous les outils) ou "user" (sans terminal,
  fichiers, Docker ni services) ;
- un utilisateur : à qui appartiennent la conversation, la mémoire, les
  tâches (par défaut "owner", le propriétaire) ;
- l'option « confiance » : l'application peut parler au nom de SES
  utilisateurs avec l'en-tête X-Jarvis-User (ex. Nexus et ses comptes).
  Le rôle demandé ne peut jamais dépasser le rôle de la clé.

Seule l'empreinte SHA-256 de la clé est stockée : une clé perdue ne
peut pas être retrouvée, il faut en créer une nouvelle.
"""

import hashlib
import re
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

NAME = re.compile(r"[a-z0-9][a-z0-9_\-]{0,31}")
USER = re.compile(r"[A-Za-z0-9_\-]{1,64}")
PREFIX = "jv_"


@dataclass
class Client:
    name: str
    role: str
    user: str
    trusted: bool
    created_at: str
    last_used: Optional[str]


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class ClientStore:
    """Applications autorisées, dans une petite base SQLite."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    name       TEXT PRIMARY KEY,
                    key_hash   TEXT NOT NULL UNIQUE,
                    role       TEXT NOT NULL,
                    user       TEXT NOT NULL,
                    trusted    INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_used  TEXT
                )
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _client(row) -> Client:
        return Client(row["name"], row["role"], row["user"], bool(row["trusted"]),
                      row["created_at"], row["last_used"])

    def add(self, name: str, role: str = "admin", user: str = "owner",
            trusted: bool = False) -> str:
        """Crée une application et retourne sa clé (affichée une seule fois)."""
        name = name.strip().lower()
        if not NAME.fullmatch(name):
            raise ValueError("nom invalide : lettres minuscules, chiffres, _ ou - (32 max)")
        if role not in ("admin", "user"):
            raise ValueError("rôle invalide : admin ou user")
        if not USER.fullmatch(user):
            raise ValueError("utilisateur invalide : lettres, chiffres, _ ou - (64 max)")
        key = PREFIX + secrets.token_urlsafe(32)
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO clients (name, key_hash, role, user, trusted, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (name, _hash(key), role, user, int(trusted),
                     datetime.now().isoformat(timespec="seconds")),
                )
        except sqlite3.IntegrityError:
            raise ValueError(f"l'application « {name} » existe déjà")
        return key

    def remove(self, name: str) -> bool:
        with self._connect() as conn:
            return conn.execute("DELETE FROM clients WHERE name = ?",
                                (name.strip().lower(),)).rowcount > 0

    def list(self) -> list[Client]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
        return [self._client(r) for r in rows]

    def authenticate(self, key: str) -> Optional[Client]:
        """
        Application correspondant à la clé, ou None.

        La recherche se fait sur l'empreinte SHA-256 : la clé elle-même
        n'est jamais stockée ni comparée en clair.
        """
        if not key or not key.startswith(PREFIX):
            return None
        digest = _hash(key)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM clients WHERE key_hash = ?",
                               (digest,)).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE clients SET last_used = ? WHERE name = ?",
                         (datetime.now().isoformat(timespec="seconds"), row["name"]))
        return self._client(row)
