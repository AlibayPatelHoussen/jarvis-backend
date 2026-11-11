"""
core/environment.py
===================
Découverte de l'environnement où Jarvis tourne.

Au démarrage, Jarvis regarde seul où il est : système d'exploitation,
machine, dossier de travail, logiciels présents (git, docker,
systemctl, ffmpeg...). Ce résumé est ajouté à son prompt système :
il sait alors quelles commandes ont du sens sur CETTE machine, et
seuls les outils utilisables ici lui sont proposés (pas d'outil
Docker si Docker n'est pas installé).
"""

import getpass
import os
import platform
import shutil
import socket
from dataclasses import dataclass, field
from pathlib import Path

# Logiciels intéressants à détecter, par catégorie
KNOWN_PROGRAMS = {
    "conteneurs": ["docker", "podman", "docker-compose", "kubectl"],
    "services": ["systemctl", "service", "launchctl", "sc"],
    "paquets": ["apt", "dnf", "pacman", "brew", "winget", "choco", "snap"],
    "développement": ["git", "python3", "python", "node", "npm", "pip"],
    "réseau": ["curl", "wget", "ssh", "ping", "nginx", "caddy"],
    "multimédia": ["ffmpeg", "yt-dlp", "vlc", "mpv"],
}


@dataclass
class Environment:
    os_name: str
    os_version: str
    hostname: str
    user: str
    shell: str
    cwd: Path
    workspace: Path
    programs: dict[str, list[str]] = field(default_factory=dict)

    def has(self, program: str) -> bool:
        return any(program in found for found in self.programs.values())

    def summary(self) -> str:
        """Résumé pour le prompt système et la commande /environnement."""
        lines = [
            "Environnement (découvert automatiquement) :",
            f"- Système : {self.os_name} {self.os_version}",
            f"- Machine : {self.hostname} (utilisateur {self.user})",
            f"- Shell   : {self.shell}",
            f"- Dossier de travail autorisé pour les fichiers : {self.workspace}",
        ]
        found = [f"{cat} : {', '.join(progs)}" for cat, progs in self.programs.items() if progs]
        if found:
            lines.append("- Logiciels disponibles :")
            lines += [f"  - {line}" for line in found]
        lines.append(
            "- Adapte les commandes que tu proposes à ce système "
            "(ex. pas de commande Linux sous Windows)."
        )
        return "\n".join(lines)


def discover(workspace: Path = None) -> Environment:
    """Inspecte la machine (rapide : aucune commande n'est lancée)."""
    system = platform.system() or "Inconnu"
    names = {"Darwin": "macOS"}
    if system == "Windows":
        shell = os.environ.get("COMSPEC", "cmd.exe")
    else:
        shell = os.environ.get("SHELL", "/bin/sh")
    try:
        user = getpass.getuser()
    except Exception:
        user = "inconnu"

    programs = {
        category: [p for p in candidates if shutil.which(p)]
        for category, candidates in KNOWN_PROGRAMS.items()
    }
    return Environment(
        os_name=names.get(system, system),
        os_version=platform.release(),
        hostname=socket.gethostname(),
        user=user,
        shell=shell,
        cwd=Path.cwd(),
        workspace=Path(workspace or Path.home()).expanduser().resolve(),
        programs=programs,
    )
