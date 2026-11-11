"""
tools/system.py
===============
Outils système : état de la machine, processus, commandes, Docker,
services. Pensés pour un serveur auto-hébergé (ex. piloté par Nexus).

Règles de sécurité :
- Les outils de LECTURE (état, processus, liste des conteneurs, état
  d'un service) s'exécutent directement.
- Tout ce qui MODIFIE la machine (commande libre, redémarrage d'un
  conteneur) demande la confirmation de l'utilisateur.
- Les outils Docker / services ne sont proposés que si le logiciel
  correspondant est installé (voir core/environment.py).
"""

import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from core.environment import Environment

try:
    import psutil
except ImportError:  # optionnel : infos plus limitées sans psutil
    psutil = None

# Taille maximale d'une sortie renvoyée au modèle
MAX_OUTPUT = 4000
# Noms acceptés pour un conteneur ou un service (évite toute injection)
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@\-]{0,127}")


def _truncate(text: str, limit: int = MAX_OUTPUT) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... (sortie tronquée, {len(text) - limit} caractères de plus)"


def _gb(n_bytes: float) -> str:
    return f"{n_bytes / 1024 ** 3:.1f} Go"


def _format_duration(seconds: float) -> str:
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts = [f"{days} j"] if days else []
    parts.append(f"{hours} h {minutes:02d}")
    return " ".join(parts)


def run_command(args, timeout: int = 30, cwd: Optional[Path] = None, shell: bool = False) -> str:
    """Lance une commande et retourne code de sortie + sorties (tronquées)."""
    try:
        proc = subprocess.run(
            args, shell=shell, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, errors="replace",
        )
    except subprocess.TimeoutExpired:
        return f"Erreur : la commande a dépassé {timeout} s et a été arrêtée."
    except FileNotFoundError as e:
        return f"Erreur : programme introuvable ({e.filename})."
    out = []
    if proc.stdout.strip():
        out.append(proc.stdout)
    if proc.stderr.strip():
        out.append("[erreurs]\n" + proc.stderr)
    body = _truncate("\n".join(out)) if out else "(aucune sortie)"
    return f"Code de sortie : {proc.returncode}\n{body}"


def system_info() -> str:
    """Résumé de l'état de la machine."""
    lines = [
        f"Système : {platform.system()} {platform.release()} ({platform.machine()})",
        f"Machine : {platform.node()}",
        f"Processeurs : {os.cpu_count()}",
    ]
    if psutil:
        lines.append(f"CPU utilisé : {psutil.cpu_percent(interval=0.3):.0f} %")
        mem = psutil.virtual_memory()
        lines.append(f"Mémoire : {_gb(mem.used)} / {_gb(mem.total)} ({mem.percent:.0f} %)")
        lines.append(f"Allumée depuis : {_format_duration(time.time() - psutil.boot_time())}")
    if hasattr(os, "getloadavg"):
        load = ", ".join(f"{x:.2f}" for x in os.getloadavg())
        lines.append(f"Charge (1, 5, 15 min) : {load}")
    lines.append(disk_usage())
    if not psutil:
        lines.append("(Installez psutil pour plus de détails : pip install psutil)")
    return "\n".join(lines)


def disk_usage(path: str = "") -> str:
    """Occupation des disques (tous les disques si psutil, sinon `path` ou la racine)."""
    targets = []
    if path:
        targets = [path]
    elif psutil:
        seen = set()
        for part in psutil.disk_partitions(all=False):
            skip = part.mountpoint.startswith(("/snap", "/boot/efi"))
            if part.mountpoint not in seen and not skip:
                seen.add(part.mountpoint)
                targets.append(part.mountpoint)
    if not targets:
        targets = [os.path.abspath(os.sep)]
    lines = ["Disques :"]
    for target in targets:
        try:
            usage = shutil.disk_usage(target)
        except OSError as e:
            lines.append(f"- {target} : inaccessible ({e})")
            continue
        # Sans chemin précis, on masque les petits montages virtuels (< 1 Go)
        if not path and len(targets) > 1 and usage.total < 1024 ** 3:
            continue
        percent = usage.used / usage.total * 100 if usage.total else 0
        lines.append(
            f"- {target} : {_gb(usage.used)} / {_gb(usage.total)} utilisés "
            f"({percent:.0f} %), {_gb(usage.free)} libres"
        )
    return "\n".join(lines)


def top_processes(sort: str = "cpu", count: int = 10) -> str:
    if not psutil:
        return "Erreur : psutil n'est pas installé (pip install psutil)."
    key = "memory_percent" if sort.lower().startswith(("m", "r")) else "cpu_percent"
    procs = list(psutil.process_iter(["pid", "name", "username"]))
    for p in procs:  # première mesure CPU
        try:
            p.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(0.3)
    rows = []
    for p in procs:
        try:
            rows.append((p.info["pid"], p.info["name"] or "?",
                         p.cpu_percent(None), p.memory_percent()))
        except psutil.Error:
            continue
    index = 3 if key == "memory_percent" else 2
    rows.sort(key=lambda r: r[index], reverse=True)
    lines = ["PID      CPU %  MÉM %  NOM"]
    for pid, name, cpu, mem in rows[:max(1, min(count, 50))]:
        lines.append(f"{pid:<8} {cpu:5.1f}  {mem:5.1f}  {name}")
    return "\n".join(lines)


def register_system_tools(registry, env: Environment, command_timeout: int = 30,
                          allow_commands: bool = True):
    """Ajoute les outils système adaptés à cette machine."""

    @registry.tool()
    def infos_systeme() -> str:
        """
        Donne l'état de la machine : système, processeur, mémoire, disques,
        durée depuis le démarrage, charge.
        """
        return system_info()

    @registry.tool()
    def espace_disque(chemin: str = "") -> str:
        """
        Donne l'espace utilisé et libre sur les disques.

        Args:
            chemin : Optionnel. Dossier ou point de montage précis.
        """
        return disk_usage(chemin)

    @registry.tool()
    def processus(tri: str = "cpu", nombre: int = 10) -> str:
        """
        Liste les processus qui consomment le plus.

        Args:
            tri    : "cpu" ou "memoire"
            nombre : Nombre de processus à afficher (max 50)
        """
        return top_processes(tri, nombre)

    if allow_commands:
        @registry.tool(confirm=True)
        def executer_commande(commande: str, dossier: str = "") -> str:
            """
            Exécute une commande dans le terminal de la machine et renvoie
            sa sortie. L'utilisateur doit confirmer chaque commande. Utilise
            des commandes adaptées au système (voir Environnement).

            Args:
                commande : Commande complète, ex. "ls -la" ou "git status"
                dossier  : Optionnel. Dossier où lancer la commande.
            """
            cwd = Path(dossier).expanduser() if dossier else env.workspace
            if not cwd.is_dir():
                return f"Erreur : dossier introuvable : {cwd}"
            return run_command(commande, timeout=command_timeout, cwd=cwd, shell=True)

    if env.has("docker"):
        @registry.tool()
        def conteneurs_docker(tous: bool = False) -> str:
            """
            Liste les conteneurs Docker avec leur état et leur image.

            Args:
                tous : true pour inclure les conteneurs arrêtés
            """
            args = ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"]
            if tous:
                args.insert(2, "-a")
            return run_command(args, timeout=command_timeout)

        @registry.tool()
        def journaux_conteneur(nom: str, lignes: int = 50) -> str:
            """
            Affiche les derniers journaux (logs) d'un conteneur Docker.

            Args:
                nom    : Nom du conteneur (voir conteneurs_docker)
                lignes : Nombre de lignes (max 500)
            """
            if not SAFE_NAME.fullmatch(nom):
                return f"Erreur : nom de conteneur invalide : {nom!r}"
            lines = str(max(1, min(lignes, 500)))
            return run_command(["docker", "logs", "--tail", lines, nom], timeout=command_timeout)

        @registry.tool(confirm=True)
        def redemarrer_conteneur(nom: str) -> str:
            """
            Redémarre un conteneur Docker. L'utilisateur doit confirmer.

            Args:
                nom : Nom du conteneur (voir conteneurs_docker)
            """
            if not SAFE_NAME.fullmatch(nom):
                return f"Erreur : nom de conteneur invalide : {nom!r}"
            return run_command(["docker", "restart", nom], timeout=max(command_timeout, 60))

    if env.has("systemctl"):
        @registry.tool()
        def etat_service(nom: str) -> str:
            """
            Donne l'état d'un service système (systemd), ex. nginx, ssh.

            Args:
                nom : Nom du service
            """
            if not SAFE_NAME.fullmatch(nom):
                return f"Erreur : nom de service invalide : {nom!r}"
            return run_command(
                ["systemctl", "status", nom, "--no-pager", "--lines", "10"],
                timeout=command_timeout,
            )

    return registry
