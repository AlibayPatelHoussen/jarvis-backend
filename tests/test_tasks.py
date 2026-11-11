"""
tests/test_tasks.py
===================
Tests unitaires pour tools/tasks.py
"""

from datetime import datetime, timedelta

import pytest

from tools.registry import ToolRegistry
from tools.tasks import (
    ReminderScheduler, TaskStore, format_tasks, format_when, parse_when,
    register_task_tools,
)

# Mercredi 11 novembre 2026, 14 h 00
NOW = datetime(2026, 11, 11, 14, 0)


@pytest.fixture
def store(tmp_path):
    return TaskStore(tmp_path / "jarvis.db")


@pytest.fixture
def tools(store):
    return register_task_tools(ToolRegistry(), store)


# ─────────────────────────────────────────────
# Lecture des dates
# ─────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("2026-11-12T09:00", datetime(2026, 11, 12, 9, 0)),
    ("2026-11-12 09:30", datetime(2026, 11, 12, 9, 30)),
    ("2026-11-12", datetime(2026, 11, 12)),
    ("dans 10 minutes", NOW + timedelta(minutes=10)),
    ("dans 2 h", NOW + timedelta(hours=2)),
    ("dans 1,5 heures", NOW + timedelta(hours=1.5)),
    ("dans 3 jours", NOW + timedelta(days=3)),
    ("dans 30 secondes", NOW + timedelta(seconds=30)),
    ("16h30", datetime(2026, 11, 11, 16, 30)),
    ("à 18:05", datetime(2026, 11, 11, 18, 5)),
    ("9h", datetime(2026, 11, 12, 9, 0)),  # déjà passé → demain
    ("demain", datetime(2026, 11, 12, 9, 0)),
    ("Demain à 7h45", datetime(2026, 11, 12, 7, 45)),
    ("après-demain 18h", datetime(2026, 11, 13, 18, 0)),
    ("ce soir", datetime(2026, 11, 11, 20, 0)),
    ("vendredi 18h", datetime(2026, 11, 13, 18, 0)),
    ("mercredi 10h", datetime(2026, 11, 18, 10, 0)),  # aujourd'hui = mercredi → suivant
])
def test_parse_when(text, expected):
    assert parse_when(text, now=NOW) == expected


@pytest.mark.parametrize("text", ["", "un jour", "dans 3 lunes", "demain à 25h", "14h75"])
def test_parse_when_errors(text):
    with pytest.raises(ValueError):
        parse_when(text, now=NOW)


def test_format_when():
    assert format_when(datetime(2026, 11, 11, 16, 5), now=NOW) == "aujourd'hui à 16 h 05"
    assert format_when(datetime(2026, 11, 12, 9, 0), now=NOW) == "demain à 9 h 00"
    expected = "vendredi 20 novembre 2026 à 8 h 00"
    assert format_when(datetime(2026, 11, 20, 8, 0), now=NOW) == expected


# ─────────────────────────────────────────────
# Tâches
# ─────────────────────────────────────────────

def test_tasks_crud_and_order(store):
    a = store.add_task("Faire les courses")
    b = store.add_task("Payer le loyer", due=datetime(2026, 11, 13, 18), priority="haute")
    c = store.add_task("Rappeler le garage", priority="inconnue")
    assert [t["id"] for t in store.list_tasks()] == [b, a, c]
    assert store.list_tasks()[2]["priority"] == "normale"
    assert store.complete_task(a) == "Faire les courses"
    assert [t["id"] for t in store.list_tasks()] == [b, c]
    assert len(store.list_tasks(include_done=True)) == 3
    assert store.delete_task(c) == "Rappeler le garage"
    assert store.complete_task(999) is None and store.delete_task(999) is None
    with pytest.raises(ValueError):
        store.add_task("  ")


def test_format_tasks(store):
    store.add_task("Payer le loyer", due=datetime(2030, 1, 4, 18), priority="haute")
    task_id = store.add_task("Courses")
    store.complete_task(task_id)
    text = format_tasks(store.list_tasks(include_done=True))
    expected = "[ ] #1 Payer le loyer (priorité haute, pour vendredi 4 janvier 2030 à 18 h 00)"
    assert expected in text
    assert "[x] #2 Courses" in text
    assert format_tasks([]) == "Aucune tâche."


def test_task_tools(tools, store):
    result = tools.execute("ajouter_tache", {
        "titre": "Payer le loyer", "echeance": "2030-01-04T18:00", "priorite": "Haute",
    })
    assert result.startswith("Tâche #1 ajoutée")
    assert store.list_tasks()[0]["priority"] == "haute"
    assert "Payer le loyer" in tools.execute("lister_taches")
    assert tools.execute("terminer_tache", {"id": "1"}) == "Tâche #1 terminée : Payer le loyer"
    assert tools.execute("lister_taches") == "Aucune tâche."
    assert "[x]" in tools.execute("lister_taches", {"inclure_terminees": True})
    assert tools.execute("supprimer_tache", {"id": 1}).startswith("Tâche #1 supprimée")
    assert "introuvable" in tools.execute("terminer_tache", {"id": 1})
    result = tools.execute("ajouter_tache", {"titre": "x", "echeance": "bientôt"})
    assert "date non comprise" in result


# ─────────────────────────────────────────────
# Rappels
# ─────────────────────────────────────────────

def test_reminders(store):
    past = store.add_reminder("Passé", datetime.now() - timedelta(minutes=1))
    future = store.add_reminder("Futur", datetime.now() + timedelta(hours=1))
    assert [r.id for r in store.pending_reminders()] == [past, future]
    due = store.pop_due_reminders()
    assert [r.message for r in due] == ["Passé"]
    assert store.pop_due_reminders() == []  # délivré une seule fois
    assert store.cancel_reminder(future) == "Futur"
    assert store.pending_reminders() == []
    assert store.cancel_reminder(past) is None  # déjà délivré


def test_reminder_tools(tools, store):
    result = tools.execute("creer_rappel", {"message": "Appeler maman", "quand": "dans 20 minutes"})
    assert result.startswith("Rappel #1 programmé") and "Appeler maman" in result
    assert "Appeler maman" in tools.execute("lister_rappels")
    assert "déjà passé" in tools.execute("creer_rappel", {"message": "x", "quand": "2000-01-01"})
    assert tools.execute("annuler_rappel", {"id": 1}) == "Rappel #1 annulé : Appeler maman"
    assert tools.execute("lister_rappels") == "Aucun rappel en attente."


def test_scheduler_delivers_due_reminders(store):
    import threading
    got = []
    done = threading.Event()
    store.add_reminder("Manqué pendant la fermeture", datetime.now() - timedelta(hours=2))
    store.add_reminder("Plus tard", datetime.now() + timedelta(hours=2))

    def notify(reminder):
        got.append(reminder.message)
        done.set()

    scheduler = ReminderScheduler(store, notify, interval=0.05).start()
    assert done.wait(2)
    scheduler.stop()
    assert got == ["Manqué pendant la fermeture"]


def test_scheduler_survives_notify_errors(store):
    store.add_reminder("x", datetime.now() - timedelta(seconds=1))
    scheduler = ReminderScheduler(store, lambda r: 1 / 0)
    assert scheduler.check() == 1


# ─────────────────────────────────────────────
# Notes
# ─────────────────────────────────────────────

def test_notes(tools, store):
    assert tools.execute("prendre_note", {"contenu": "Code wifi : 1234", "titre": "Maison"}) \
        == "Note #1 enregistrée."
    tools.execute("prendre_note", {"contenu": "Lait, œufs, pain", "titre": "Courses"})
    assert "#2 Courses — Lait, œufs, pain" in tools.execute("chercher_notes")
    assert tools.execute("chercher_notes", {"recherche": "wifi maison"}) \
        == "#1 Maison — Code wifi : 1234"
    assert tools.execute("chercher_notes", {"recherche": "voiture"}) == "Aucune note trouvée."
    assert store.delete_note(1) is True and store.delete_note(1) is False


def test_tasks_share_the_memory_database(tmp_path):
    from core.brain import Brain
    from core.memory import LongTermMemory
    brain = Brain(long_term=LongTermMemory(db_path=tmp_path / "memory.db"))
    assert brain.tasks.db_path == tmp_path / "memory.db"
    assert "ajouter_tache" in brain.tools and "creer_rappel" in brain.tools
