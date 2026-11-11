"""
tests/test_memory.py
====================
Tests unitaires pour core/memory.py
"""

from core.memory import ShortTermMemory, LongTermMemory


# ─────────────────────────────────────────────
# Tests ShortTermMemory
# ─────────────────────────────────────────────

def test_short_term_starts_empty():
    """L'historique doit être vide au départ."""
    mem = ShortTermMemory()
    assert mem.count() == 0


def test_short_term_add_message():
    """On doit pouvoir ajouter un message."""
    mem = ShortTermMemory()
    mem.add("user", "Bonjour")
    assert mem.count() == 1


def test_short_term_get_history():
    """get_history() doit retourner les bons messages."""
    mem = ShortTermMemory()
    mem.add("user", "Bonjour")
    mem.add("assistant", "Bonjour !")

    history = mem.get_history()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Bonjour"
    assert history[1]["role"] == "assistant"


def test_short_term_clear():
    """clear() doit vider l'historique."""
    mem = ShortTermMemory()
    mem.add("user", "test")
    mem.clear()
    assert mem.count() == 0


def test_short_term_max_messages():
    """L'historique ne doit pas dépasser max_messages."""
    mem = ShortTermMemory(max_messages=4)
    for i in range(10):
        mem.add("user", f"message {i}")
    assert mem.count() == 4


def test_short_term_keeps_latest():
    """On doit garder les messages les plus récents."""
    mem = ShortTermMemory(max_messages=2)
    mem.add("user", "ancien")
    mem.add("user", "récent")
    mem.add("user", "très récent")

    history = mem.get_history()
    contents = [m["content"] for m in history]
    assert "très récent" in contents
    assert "ancien" not in contents


# ─────────────────────────────────────────────
# Tests LongTermMemory
# ─────────────────────────────────────────────

def make_temp_memory() -> LongTermMemory:
    """Crée une LongTermMemory avec une DB temporaire pour les tests."""
    import tempfile
    from pathlib import Path
    return LongTermMemory(db_path=Path(tempfile.mkdtemp()) / "memory.db")


def test_long_term_starts_empty():
    """La DB doit être vide au départ."""
    mem = make_temp_memory()
    assert mem.count() == 0


def test_long_term_save_and_get():
    """On doit pouvoir sauvegarder et récupérer un fait."""
    mem = make_temp_memory()
    mem.save("prenom", "Houssen")
    assert mem.get("prenom") == "Houssen"


def test_long_term_get_unknown_key():
    """get() doit retourner None pour une clé inconnue."""
    mem = make_temp_memory()
    assert mem.get("inconnu") is None


def test_long_term_update_existing():
    """Sauvegarder une clé existante doit mettre à jour la valeur."""
    mem = make_temp_memory()
    mem.save("ville", "Paris")
    mem.save("ville", "Montréal")
    assert mem.get("ville") == "Montréal"


def test_long_term_get_all():
    """get_all() doit retourner tous les faits."""
    mem = make_temp_memory()
    mem.save("prenom", "Houssen")
    mem.save("ville", "Montréal")

    facts = mem.get_all()
    assert facts["prenom"] == "Houssen"
    assert facts["ville"] == "Montréal"


def test_long_term_delete():
    """delete() doit supprimer un fait."""
    mem = make_temp_memory()
    mem.save("prenom", "Houssen")
    result = mem.delete("prenom")
    assert result is True
    assert mem.get("prenom") is None


def test_long_term_delete_unknown():
    """delete() doit retourner False pour une clé inconnue."""
    mem = make_temp_memory()
    assert mem.delete("inconnu") is False


def test_long_term_count():
    """count() doit retourner le bon nombre de faits."""
    mem = make_temp_memory()
    mem.save("a", "1")
    mem.save("b", "2")
    mem.save("c", "3")
    assert mem.count() == 3


# ─────────────────────────────────────────────
# Non-régression
# ─────────────────────────────────────────────

def test_long_term_closes_connections(monkeypatch):
    """Chaque opération doit fermer sa connexion SQLite."""
    import sqlite3
    opened = []
    real_connect = sqlite3.connect

    class Tracked:
        def __init__(self, conn):
            self._conn = conn
            self.closed = False

        def close(self):
            self.closed = True
            self._conn.close()

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def __enter__(self):
            self._conn.__enter__()
            return self

        def __exit__(self, *args):
            return self._conn.__exit__(*args)

    def connect(*args, **kwargs):
        conn = Tracked(real_connect(*args, **kwargs))
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    mem = make_temp_memory()
    mem.save("a", "1")
    mem.get("a")
    mem.get_all()
    mem.delete("a")
    mem.count()
    assert opened and all(c.closed for c in opened)


def test_long_term_get_all_keeps_insertion_order():
    mem = make_temp_memory()
    for key in ["z", "a", "m"]:
        mem.save(key, key.upper())
    assert list(mem.get_all()) == ["z", "a", "m"]
