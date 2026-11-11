"""
tests/test_system_tools.py
==========================
Tests unitaires pour tools/system.py
"""

import sys
from pathlib import Path

import pytest

from core.environment import Environment
from tools import system
from tools.registry import ToolRegistry
from tools.system import register_system_tools, run_command


def make_env(tmp_path, programs=None):
    return Environment(
        os_name="Linux", os_version="6", hostname="h", user="u", shell="/bin/sh",
        cwd=tmp_path, workspace=tmp_path, programs=programs or {},
    )


@pytest.fixture
def calls(monkeypatch):
    """Remplace run_command pour voir les commandes sans les lancer."""
    seen = []

    def fake(args, timeout=30, cwd=None, shell=False):
        seen.append({"args": args, "cwd": cwd, "shell": shell, "timeout": timeout})
        return "Code de sortie : 0\nok"

    monkeypatch.setattr(system, "run_command", fake)
    return seen


def test_tools_depend_on_installed_programs(tmp_path):
    bare = register_system_tools(ToolRegistry(), make_env(tmp_path))
    assert bare.names() == ["espace_disque", "executer_commande", "infos_systeme", "processus"]
    full = register_system_tools(
        ToolRegistry(),
        make_env(tmp_path, {"conteneurs": ["docker"], "services": ["systemctl"]}),
    )
    assert {"conteneurs_docker", "journaux_conteneur", "redemarrer_conteneur",
            "etat_service"} <= set(full.names())
    no_cmd = register_system_tools(ToolRegistry(), make_env(tmp_path), allow_commands=False)
    assert "executer_commande" not in no_cmd


def test_sensitive_tools_require_confirmation(tmp_path):
    reg = register_system_tools(ToolRegistry(), make_env(tmp_path, {"c": ["docker"]}))
    assert reg.get("executer_commande").confirm is True
    assert reg.get("redemarrer_conteneur").confirm is True
    assert reg.get("conteneurs_docker").confirm is False
    assert reg.execute("executer_commande", {"commande": "rm -rf /"}) \
        == "Action refusée par l'utilisateur."


def test_info_tools_return_text(tmp_path):
    reg = register_system_tools(ToolRegistry(), make_env(tmp_path))
    info = reg.execute("infos_systeme")
    assert "Système :" in info and "Disques :" in info
    assert "Disques :" in reg.execute("espace_disque", {"chemin": str(tmp_path)})
    assert reg.execute("processus", {"nombre": 3}).startswith("PID")


def test_docker_and_service_commands(tmp_path, calls):
    reg = register_system_tools(
        ToolRegistry(), make_env(tmp_path, {"c": ["docker"], "s": ["systemctl"]}),
        command_timeout=12,
    )
    reg.execute("conteneurs_docker", {"tous": True})
    reg.execute("journaux_conteneur", {"nom": "jellyfin", "lignes": 9999})
    reg.execute("redemarrer_conteneur", {"nom": "jellyfin"}, confirm=lambda s: True)
    reg.execute("etat_service", {"nom": "nginx"})
    args = [c["args"] for c in calls]
    assert args[0][:3] == ["docker", "ps", "-a"]
    assert args[1] == ["docker", "logs", "--tail", "500", "jellyfin"]
    assert args[2] == ["docker", "restart", "jellyfin"]
    assert args[3][:3] == ["systemctl", "status", "nginx"]
    assert all(not c["shell"] for c in calls)


@pytest.mark.parametrize("name", ["jelly fin", "a;rm -rf /", "$(id)", "-h", ""])
def test_container_and_service_names_are_validated(tmp_path, calls, name):
    reg = register_system_tools(
        ToolRegistry(), make_env(tmp_path, {"c": ["docker"], "s": ["systemctl"]}))
    assert "invalide" in reg.execute("journaux_conteneur", {"nom": name})
    assert "invalide" in reg.execute("etat_service", {"nom": name})
    assert calls == []


def test_executer_commande_runs_in_workspace(tmp_path):
    reg = register_system_tools(ToolRegistry(), make_env(tmp_path))
    (tmp_path / "fichier.txt").write_text("x")
    cmd = f'"{sys.executable}" -c "import os; print(sorted(os.listdir()))"'
    result = reg.execute("executer_commande", {"commande": cmd}, confirm=lambda s: True)
    assert result.startswith("Code de sortie : 0") and "fichier.txt" in result
    missing = reg.execute("executer_commande", {"commande": "ls", "dossier": "/nulle/part"},
                          confirm=lambda s: True)
    assert "dossier introuvable" in missing


def test_run_command_timeout_errors_and_truncation(tmp_path):
    slow = run_command([sys.executable, "-c", "import time; time.sleep(5)"], timeout=1)
    assert "dépassé 1 s" in slow
    assert "introuvable" in run_command(["programme-qui-n-existe-pas"])
    failing = run_command([sys.executable, "-c", "import sys; sys.exit('oups')"])
    assert failing.startswith("Code de sortie : 1") and "[erreurs]" in failing
    big = run_command([sys.executable, "-c", "print('a' * 10000)"])
    assert "sortie tronquée" in big and len(big) < 4200
    assert Path(tmp_path).exists()
