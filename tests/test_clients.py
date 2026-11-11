"""
tests/test_clients.py
=====================
Tests unitaires pour core/clients.py
"""

import sqlite3

import pytest

from core.clients import ClientStore


@pytest.fixture
def store(tmp_path):
    return ClientStore(tmp_path / "clients.db")


def test_add_and_authenticate(store):
    key = store.add("Telephone")
    assert key.startswith("jv_") and len(key) > 40
    client = store.authenticate(key)
    assert (client.name, client.role, client.user, client.trusted) == \
        ("telephone", "admin", "owner", False)
    assert store.list()[0].last_used is not None


def test_bad_keys(store):
    store.add("nexus")
    for key in ["", "jv_faux", "pas-une-cle", "jv_" + "a" * 43]:
        assert store.authenticate(key) is None


def test_key_is_not_stored_in_clear(store, tmp_path):
    key = store.add("nexus", role="user", user="42", trusted=True)
    conn = sqlite3.connect(tmp_path / "clients.db")
    dump = "\n".join(conn.iterdump())
    conn.close()
    assert key not in dump and key[3:] not in dump


@pytest.mark.parametrize("kwargs, error", [
    ({"name": "Mon Appli"}, "nom invalide"),
    ({"name": "x" * 40}, "nom invalide"),
    ({"name": "app", "role": "root"}, "rôle invalide"),
    ({"name": "app", "user": "../etc"}, "utilisateur invalide"),
])
def test_validation(store, kwargs, error):
    with pytest.raises(ValueError, match=error):
        store.add(**kwargs)


def test_duplicates_and_remove(store):
    key = store.add("nexus")
    with pytest.raises(ValueError, match="existe déjà"):
        store.add("Nexus")
    assert store.remove("NEXUS") is True
    assert store.authenticate(key) is None
    assert store.remove("nexus") is False
