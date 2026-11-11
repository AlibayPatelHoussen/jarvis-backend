"""
core/sessions.py
================
Un Jarvis par utilisateur, pour le mode serveur.

Chaque utilisateur a sa propre conversation, sa mémoire, ses tâches,
rappels et notes (data/users/<id>/memory.db), et des outils selon son
rôle ("admin" ou "user"). La clé principale parle au nom du
propriétaire ("owner", admin) ; une application de confiance comme
Nexus transmet l'identité de chacun de ses utilisateurs.
"""

import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from core.brain import Brain
from core.environment import Environment
from core.memory import LongTermMemory
from tools.tasks import Reminder, TaskStore

USER_ID = re.compile(r"[A-Za-z0-9_\-]{1,64}")


class SessionError(ValueError):
    pass


@dataclass
class Session:
    user_id: str
    role: str
    brain: Brain
    # Un seul message traité à la fois par utilisateur
    lock: threading.Lock = field(default_factory=threading.Lock)


class SessionManager:
    """Crée et garde un Brain par utilisateur."""

    def __init__(self, data_dir: Path, environment: Environment,
                 llm_factory: Callable[[], object]):
        self.data_dir = Path(data_dir)
        self.environment = environment
        self.llm_factory = llm_factory
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def user_db(self, user_id: str) -> Path:
        if not USER_ID.fullmatch(user_id or ""):
            raise SessionError(f"identifiant d'utilisateur invalide : {user_id!r}")
        folder = self.data_dir / "users" / user_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "memory.db"

    def get(self, user_id: str, role: str = "user", name: Optional[str] = None) -> Session:
        if role not in ("admin", "user"):
            raise SessionError(f"rôle invalide : {role!r}")
        # Seul le propriétaire prend le prénom de JARVIS_USER_NAME par défaut ;
        # un autre utilisateur sans prénom est désigné par son identifiant.
        if not name and user_id != "owner":
            name = user_id
        with self._lock:
            session = self._sessions.get(user_id)
            # Un changement de rôle (ex. promu admin) reconstruit les outils
            if session is None or session.role != role:
                memory = LongTermMemory(db_path=self.user_db(user_id))
                brain = Brain(
                    llm=self.llm_factory(),
                    long_term=memory,
                    environment=self.environment,
                    role=role,
                    user_name=name or None,
                )
                if session is not None:  # garder la conversation en cours
                    brain.short_term = session.brain.short_term
                session = Session(user_id=user_id, role=role, brain=brain)
                self._sessions[user_id] = session
            elif name:
                session.brain.user_name = name
            return session

    def known_users(self) -> list[str]:
        """Utilisateurs ayant des données (même s'ils ne sont pas connectés)."""
        users_dir = self.data_dir / "users"
        if not users_dir.is_dir():
            return []
        return sorted(p.name for p in users_dir.iterdir()
                      if (p / "memory.db").exists() and USER_ID.fullmatch(p.name))


@dataclass
class Notification:
    id: int
    user_id: str
    message: str
    due_at: datetime
    # "reminder" (rappel arrivé à échéance) ou "info" (résultat d'une action…)
    kind: str = "reminder"


class NotificationCenter:
    """
    Livre les rappels en mode serveur : vérifie les bases de tous les
    utilisateurs et met les rappels échus en attente. Les interfaces
    (Nexus…) les récupèrent avec GET /api/notifications.
    """

    def __init__(self, sessions: SessionManager, interval: float = 15.0,
                 on_notify: Optional[Callable[[Notification], None]] = None):
        self.sessions = sessions
        self.interval = interval
        self.on_notify = on_notify
        self._pending: dict[str, list[Notification]] = {}
        self._next_id = 1
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="jarvis-notifications",
                                        daemon=True)

    def check(self) -> int:
        count = 0
        for user_id in self.sessions.known_users():
            store = TaskStore(self.sessions.user_db(user_id))
            for reminder in store.pop_due_reminders():
                self._add(user_id, reminder)
                count += 1
        return count

    def _add(self, user_id: str, reminder: Reminder) -> None:
        with self._lock:
            note = Notification(self._next_id, user_id, reminder.message, reminder.due_at)
            self._next_id += 1
            self._pending.setdefault(user_id, []).append(note)
        if self.on_notify:
            try:
                self.on_notify(note)
            except Exception:
                pass

    def push(self, user_id: str, message: str) -> Notification:
        """Ajoute une notification immédiate (ex. résultat d'une action autorisée)."""
        with self._lock:
            note = Notification(self._next_id, user_id, message, datetime.now(), "info")
            self._next_id += 1
            self._pending.setdefault(user_id, []).append(note)
        if self.on_notify:
            try:
                self.on_notify(note)
            except Exception:
                pass
        return note

    def pop(self, user_id: str) -> list[Notification]:
        with self._lock:
            return self._pending.pop(user_id, [])

    def start(self) -> "NotificationCenter":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while True:
            try:
                self.check()
            except Exception:
                pass
            if self._stop.wait(self.interval):
                return
