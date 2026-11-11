"""
tools/tasks.py
==============
Aide au quotidien : tâches, rappels et notes.

Tout est stocké dans la même base SQLite que la mémoire long terme
(data/memory.db) : toutes les données de Jarvis restent au même endroit.

- Tâches   : titre, échéance et priorité optionnelles, terminée ou non
- Rappels  : message + date/heure ; un planificateur les déclenche
- Notes    : texte libre, recherche par mot-clé
"""

import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterator, Optional

from core.prompt import format_date_fr

PRIORITIES = ("basse", "normale", "haute")


# ─────────────────────────────────────────────
# Lecture des dates en langage courant
# ─────────────────────────────────────────────

_UNITS = {
    "seconde": "seconds", "sec": "seconds", "s": "seconds",
    "minute": "minutes", "min": "minutes", "mn": "minutes",
    "heure": "hours", "h": "hours",
    "jour": "days", "j": "days",
    "semaine": "weeks",
}
_DAY_WORDS = {"aujourd'hui": 0, "ce soir": 0, "demain": 1, "après-demain": 2}
_WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def parse_when(text: str, now: Optional[datetime] = None) -> datetime:
    """
    Convertit une date/heure en datetime.

    Formats acceptés :
        "2026-11-12T09:00", "2026-11-12 09:00", "2026-11-12"
        "dans 10 minutes", "dans 2 h", "dans 3 jours"
        "14h30", "14:30", "à 9h" (aujourd'hui, ou demain si déjà passé)
        "demain", "demain 9h", "après-demain à 18h30", "ce soir 20h"
        "lundi 10h" (prochain lundi)

    Raises:
        ValueError : si le texte n'est pas compris
    """
    now = (now or datetime.now()).replace(microsecond=0)
    raw = text
    text = " ".join(text.strip().lower().split())
    if not text:
        raise ValueError("date vide")

    # ISO 8601
    try:
        return datetime.fromisoformat(text.upper().replace(" ", "T", 1))
    except ValueError:
        pass

    # "dans 10 minutes"
    match = re.fullmatch(r"dans (\d+(?:[.,]\d+)?) ?([a-zéû]+?)s?", text)
    if match:
        amount = float(match.group(1).replace(",", "."))
        unit = _UNITS.get(match.group(2))
        if unit:
            return now + timedelta(**{unit: amount})

    # Jour : "demain", "lundi"... suivi éventuellement d'une heure
    day_offset = None
    rest = text
    for word, offset in sorted(_DAY_WORDS.items(), key=lambda kv: -len(kv[0])):
        if rest.startswith(word):
            day_offset, rest = offset, rest[len(word):].strip()
            break
    if day_offset is None:
        for i, day in enumerate(_WEEKDAYS):
            if rest.startswith(day):
                day_offset = (i - now.weekday()) % 7 or 7
                rest = rest[len(day):].strip()
                break
    rest = re.sub(r"^(à|a|vers)\s+", "", rest)

    hour, minute = None, 0
    if rest:
        match = re.fullmatch(r"(\d{1,2})\s*(?:h|:)\s*(\d{2})?", rest)
        if not match:
            raise ValueError(f"date non comprise : {raw!r}")
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        if hour > 23 or minute > 59:
            raise ValueError(f"heure invalide : {raw!r}")

    if day_offset is None and hour is None:
        raise ValueError(f"date non comprise : {raw!r}")

    if hour is None:  # "demain" seul : 9 h du matin
        hour = 20 if text.startswith("ce soir") else 9
    result = now.replace(hour=hour, minute=minute, second=0)
    if day_offset is not None:
        result += timedelta(days=day_offset)
    elif result <= now:  # "14h" déjà passé : demain
        result += timedelta(days=1)
    return result


def format_when(when: datetime, now: Optional[datetime] = None) -> str:
    """Ex : « aujourd'hui à 14 h 30 », « demain à 9 h 00 »."""
    now = now or datetime.now()
    delta = (when.date() - now.date()).days
    time = f"{when.hour} h {when.minute:02d}"
    if delta == 0:
        return f"aujourd'hui à {time}"
    if delta == 1:
        return f"demain à {time}"
    return format_date_fr(when).replace(", ", " à ")


# ─────────────────────────────────────────────
# Stockage
# ─────────────────────────────────────────────

@dataclass
class Reminder:
    id: int
    message: str
    due_at: datetime


class TaskStore:
    """Tâches, rappels et notes dans SQLite."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    title      TEXT NOT NULL,
                    due        TEXT,
                    priority   TEXT NOT NULL DEFAULT 'normale',
                    done       INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    done_at    TEXT
                );
                CREATE TABLE IF NOT EXISTS reminders (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    message    TEXT NOT NULL,
                    due_at     TEXT NOT NULL,
                    delivered  INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notes (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    title      TEXT NOT NULL DEFAULT '',
                    content    TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    # Tâches ──────────────────────────────────

    def add_task(self, title: str, due: Optional[datetime] = None,
                 priority: str = "normale") -> int:
        title = title.strip()
        if not title:
            raise ValueError("le titre de la tâche est vide")
        if priority not in PRIORITIES:
            priority = "normale"
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO tasks (title, due, priority, created_at) VALUES (?, ?, ?, ?)",
                (title, due.isoformat(timespec="minutes") if due else None,
                 priority, self._now()),
            )
            return cursor.lastrowid

    def list_tasks(self, include_done: bool = False) -> list[dict]:
        query = "SELECT * FROM tasks"
        if not include_done:
            query += " WHERE done = 0"
        # Non terminées d'abord, puis priorité haute, puis échéance la plus proche
        query += (
            " ORDER BY done, CASE priority WHEN 'haute' THEN 0 WHEN 'normale' THEN 1"
            " ELSE 2 END, due IS NULL, due, id"
        )
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query)]

    def complete_task(self, task_id: int) -> Optional[str]:
        """Marque une tâche terminée. Retourne son titre, ou None si introuvable."""
        with self._connect() as conn:
            row = conn.execute("SELECT title FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE tasks SET done = 1, done_at = ? WHERE id = ?",
                         (self._now(), task_id))
            return row["title"]

    def delete_task(self, task_id: int) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute("SELECT title FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            return row["title"]

    # Rappels ─────────────────────────────────

    def add_reminder(self, message: str, due_at: datetime) -> int:
        message = message.strip()
        if not message:
            raise ValueError("le message du rappel est vide")
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO reminders (message, due_at, created_at) VALUES (?, ?, ?)",
                (message, due_at.isoformat(timespec="seconds"), self._now()),
            )
            return cursor.lastrowid

    def pending_reminders(self) -> list[Reminder]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, message, due_at FROM reminders WHERE delivered = 0 ORDER BY due_at"
            ).fetchall()
        return [Reminder(r["id"], r["message"], datetime.fromisoformat(r["due_at"]))
                for r in rows]

    def pop_due_reminders(self, now: Optional[datetime] = None) -> list[Reminder]:
        """Retourne les rappels arrivés à échéance et les marque comme délivrés."""
        now = now or datetime.now()
        due = [r for r in self.pending_reminders() if r.due_at <= now]
        if due:
            with self._connect() as conn:
                conn.executemany("UPDATE reminders SET delivered = 1 WHERE id = ?",
                                 [(r.id,) for r in due])
        return due

    def cancel_reminder(self, reminder_id: int) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT message FROM reminders WHERE id = ? AND delivered = 0", (reminder_id,)
            ).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            return row["message"]

    # Notes ───────────────────────────────────

    def add_note(self, content: str, title: str = "") -> int:
        content = content.strip()
        if not content:
            raise ValueError("la note est vide")
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO notes (title, content, created_at) VALUES (?, ?, ?)",
                (title.strip(), content, self._now()),
            )
            return cursor.lastrowid

    def search_notes(self, query: str = "", limit: int = 20) -> list[dict]:
        """Notes contenant tous les mots de la recherche (les plus récentes d'abord)."""
        sql = "SELECT * FROM notes"
        params: list = []
        words = query.split()
        if words:
            sql += " WHERE " + " AND ".join(["(title || ' ' || content) LIKE ?"] * len(words))
            params = [f"%{w}%" for w in words]
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, params)]

    def delete_note(self, note_id: int) -> bool:
        with self._connect() as conn:
            return conn.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount > 0


# ─────────────────────────────────────────────
# Mise en forme
# ─────────────────────────────────────────────

def format_tasks(tasks: list[dict]) -> str:
    if not tasks:
        return "Aucune tâche."
    lines = []
    for t in tasks:
        box = "[x]" if t["done"] else "[ ]"
        extra = []
        if t["priority"] == "haute":
            extra.append("priorité haute")
        if t["due"]:
            extra.append("pour " + format_when(datetime.fromisoformat(t["due"])))
        suffix = f" ({', '.join(extra)})" if extra else ""
        lines.append(f"{box} #{t['id']} {t['title']}{suffix}")
    return "\n".join(lines)


def format_reminders(reminders: list[Reminder]) -> str:
    if not reminders:
        return "Aucun rappel en attente."
    return "\n".join(f"#{r.id} {format_when(r.due_at)} : {r.message}" for r in reminders)


def format_notes(notes: list[dict]) -> str:
    if not notes:
        return "Aucune note trouvée."
    lines = []
    for n in notes:
        title = f"{n['title']} — " if n["title"] else ""
        lines.append(f"#{n['id']} {title}{n['content']}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# Outils pour le modèle
# ─────────────────────────────────────────────

def register_task_tools(registry, store: TaskStore):
    """Ajoute les outils tâches / rappels / notes au registre."""

    @registry.tool()
    def ajouter_tache(titre: str, echeance: str = "", priorite: str = "normale") -> str:
        """
        Ajoute une tâche à la liste de tâches de l'utilisateur.

        Args:
            titre    : Ce qu'il faut faire, ex. "Payer le loyer"
            echeance : Optionnel. Date limite : ISO "2026-11-12T18:00" ou
                       "demain", "vendredi 18h", "dans 3 jours"
            priorite : basse, normale ou haute
        """
        due = parse_when(echeance) if echeance.strip() else None
        task_id = store.add_task(titre, due, priorite.lower().strip())
        when = f" pour {format_when(due)}" if due else ""
        return f"Tâche #{task_id} ajoutée : {titre.strip()}{when}"

    @registry.tool()
    def lister_taches(inclure_terminees: bool = False) -> str:
        """
        Liste les tâches de l'utilisateur (non terminées par défaut).

        Args:
            inclure_terminees : true pour voir aussi les tâches terminées
        """
        return format_tasks(store.list_tasks(include_done=inclure_terminees))

    @registry.tool()
    def terminer_tache(id: int) -> str:
        """
        Marque une tâche comme terminée.

        Args:
            id : Numéro de la tâche (voir lister_taches)
        """
        title = store.complete_task(id)
        return f"Tâche #{id} terminée : {title}" if title else f"Tâche #{id} introuvable."

    @registry.tool()
    def supprimer_tache(id: int) -> str:
        """
        Supprime définitivement une tâche.

        Args:
            id : Numéro de la tâche (voir lister_taches)
        """
        title = store.delete_task(id)
        return f"Tâche #{id} supprimée : {title}" if title else f"Tâche #{id} introuvable."

    @registry.tool()
    def creer_rappel(message: str, quand: str) -> str:
        """
        Programme un rappel : Jarvis préviendra l'utilisateur à l'heure dite.
        Sert aussi de minuteur ("dans 10 minutes").

        Args:
            message : Ce qu'il faut rappeler, ex. "Appeler maman"
            quand   : ISO "2026-11-12T09:00" ou "dans 10 minutes",
                      "demain 9h", "14h30", "lundi 8h"
        """
        due = parse_when(quand)
        if due <= datetime.now():
            return f"Erreur : {format_when(due)} est déjà passé."
        reminder_id = store.add_reminder(message, due)
        return f"Rappel #{reminder_id} programmé {format_when(due)} : {message.strip()}"

    @registry.tool()
    def lister_rappels() -> str:
        """Liste les rappels programmés qui n'ont pas encore sonné."""
        return format_reminders(store.pending_reminders())

    @registry.tool()
    def annuler_rappel(id: int) -> str:
        """
        Annule un rappel programmé.

        Args:
            id : Numéro du rappel (voir lister_rappels)
        """
        message = store.cancel_reminder(id)
        return f"Rappel #{id} annulé : {message}" if message else f"Rappel #{id} introuvable."

    @registry.tool()
    def prendre_note(contenu: str, titre: str = "") -> str:
        """
        Enregistre une note (idée, liste de courses, code wifi...).

        Args:
            contenu : Texte de la note
            titre   : Titre court optionnel, ex. "Courses"
        """
        note_id = store.add_note(contenu, titre)
        return f"Note #{note_id} enregistrée."

    @registry.tool()
    def chercher_notes(recherche: str = "") -> str:
        """
        Cherche dans les notes de l'utilisateur. Vide = dernières notes.

        Args:
            recherche : Mots à chercher dans le titre ou le contenu
        """
        return format_notes(store.search_notes(recherche))

    return registry


# ─────────────────────────────────────────────
# Planificateur des rappels
# ─────────────────────────────────────────────

class ReminderScheduler:
    """
    Vérifie les rappels en arrière-plan et appelle `notify` quand
    l'un d'eux arrive à échéance. Les rappels manqués pendant que
    Jarvis était fermé sont délivrés au démarrage.
    """

    def __init__(self, store: TaskStore, notify: Callable[[Reminder], None],
                 interval: float = 15.0):
        self.store = store
        self.notify = notify
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="jarvis-rappels", daemon=True)

    def start(self) -> "ReminderScheduler":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def check(self) -> int:
        """Délivre les rappels échus. Retourne leur nombre."""
        due = self.store.pop_due_reminders()
        for reminder in due:
            try:
                self.notify(reminder)
            except Exception:
                pass
        return len(due)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.check()
            except Exception:
                pass
