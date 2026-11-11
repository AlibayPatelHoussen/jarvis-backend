"""
tests/test_environment.py
=========================
Tests unitaires pour core/environment.py
"""

from pathlib import Path

from core import environment
from core.environment import Environment, discover


def test_discover_detects_programs(monkeypatch, tmp_path):
    installed = {"docker", "git", "ffmpeg", "systemctl"}
    monkeypatch.setattr(environment.shutil, "which",
                        lambda name: f"/usr/bin/{name}" if name in installed else None)
    env = discover(tmp_path)
    assert env.workspace == tmp_path.resolve()
    assert env.has("docker") and env.has("ffmpeg") and not env.has("podman")
    assert env.programs["conteneurs"] == ["docker"]
    assert env.programs["multimédia"] == ["ffmpeg"]


def test_summary_lists_only_found_programs():
    env = Environment(
        os_name="Linux", os_version="6.1", hostname="nexus", user="houssen",
        shell="/bin/bash", cwd=Path("/"), workspace=Path("/srv"),
        programs={"conteneurs": ["docker"], "paquets": []},
    )
    text = env.summary()
    assert "Système : Linux 6.1" in text
    assert "Machine : nexus (utilisateur houssen)" in text
    assert "/srv" in text
    assert "conteneurs : docker" in text
    assert "paquets" not in text
