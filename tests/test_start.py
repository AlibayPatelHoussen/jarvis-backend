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
