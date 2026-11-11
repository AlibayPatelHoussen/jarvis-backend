"""
tests/test_start.py
===================
Tests du point d'entrée start.py
"""

import sys

import start


def test_default_runs_cli(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["start.py"])
    monkeypatch.setattr("interface.cli.run", lambda: calls.append("cli"))
    start.main()
    assert calls == ["cli"]


def test_server_option(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["start.py", "--server", "--port", "9000"])
    monkeypatch.setattr("api.server.run", lambda host=None, port=None: calls.append((host, port)))
    start.main()
    assert calls == [(None, 9000)]


def test_server_refuses_to_start_without_key(monkeypatch, capsys):
    import pytest
    from api import server
    from config import settings
    monkeypatch.setattr(settings, "API_KEY", "")
    with pytest.raises(SystemExit):
        server.run()
    assert "JARVIS_API_KEY" in capsys.readouterr().out


def test_keys_command(monkeypatch, tmp_path, capsys):
    from config import settings
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    assert start.main(["cles", "liste"]) == 0
    assert "Aucune application" in capsys.readouterr().out
    assert start.main(["cles", "ajouter", "nexus", "--role", "admin", "--confiance"]) == 0
    out = capsys.readouterr().out
    key = [line.strip() for line in out.splitlines() if line.strip().startswith("jv_")][0]
    from core.clients import ClientStore
    assert ClientStore(tmp_path / "clients.db").authenticate(key).trusted is True
    assert start.main(["cles", "ajouter", "nexus"]) == 1
    assert "existe déjà" in capsys.readouterr().out
    start.main(["cles", "liste"])
    assert "- nexus : rôle admin, utilisateur owner, confiance" in capsys.readouterr().out
    assert start.main(["cles", "supprimer", "nexus"]) == 0
    assert start.main(["cles", "supprimer", "nexus"]) == 1
    assert start.main(["cles", "ajouter"]) == 1
