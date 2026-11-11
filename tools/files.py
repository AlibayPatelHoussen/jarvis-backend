"""
tools/files.py
==============
Outils fichiers, limités à un dossier de travail autorisé
(JARVIS_WORKSPACE, par défaut le dossier personnel).

- Lire, lister, chercher : directement
- Écrire : avec confirmation de l'utilisateur

Tous les chemins sont résolus (liens symboliques et ".." compris) puis
vérifiés : impossible de sortir du dossier autorisé.
"""

import fnmatch
import functools
import os
import time
from pathlib import Path

MAX_READ_BYTES = 2_000_000      # on ne lit pas les fichiers énormes
MAX_LINES = 400                 # lignes renvoyées au modèle par lecture
MAX_RESULTS = 50
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".cache"}
# Systèmes de fichiers virtuels (immenses ou sans fin) : jamais parcourus
VIRTUAL_DIRS = {"/proc", "/sys", "/dev", "/run", "/snap"}
SEARCH_SECONDS = 20     # durée maximale d'une recherche


class WorkspaceError(Exception):
    pass


class Workspace:
    """Dossier dans lequel Jarvis a le droit de travailler."""

    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.truncated = False  # dernière recherche arrêtée par la limite de temps

    def resolve(self, path: str = ".") -> Path:
        """Chemin absolu sûr. Les chemins relatifs partent du dossier de travail."""
        candidate = Path(path or ".").expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise WorkspaceError(
                f"accès refusé : {path} est en dehors du dossier autorisé ({self.root})"
            )
        return resolved

    def display(self, path: Path) -> str:
        """Chemin relatif au dossier de travail (plus lisible)."""
        try:
            rel = path.relative_to(self.root)
            return str(rel) if str(rel) != "." else "."
        except ValueError:
            return str(path)

    def walk(self, start: Path, seconds: float = SEARCH_SECONDS):
        """
        Fichiers sous `start`. S'arrête au bout de `seconds` secondes
        (self.truncated passe alors à True) : utile quand le dossier de
        travail est la racine « / » du serveur.
        """
        self.truncated = False
        deadline = time.monotonic() + seconds
        for dirpath, dirnames, filenames in os.walk(start):
            dirnames[:] = sorted(
                d for d in dirnames
                if d not in SKIP_DIRS and os.path.join(dirpath, d) not in VIRTUAL_DIRS
            )
            if time.monotonic() > deadline:
                self.truncated = True
                return
            for name in sorted(filenames):
                yield Path(dirpath) / name


def _human_size(size: int) -> str:
    for unit in ("o", "Ko", "Mo", "Go"):
        if size < 1024 or unit == "Go":
            return f"{size:.0f} {unit}" if unit == "o" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size} o"


def _read_text(path: Path) -> str:
    if path.stat().st_size > MAX_READ_BYTES:
        raise WorkspaceError(f"fichier trop gros ({_human_size(path.stat().st_size)})")
    data = path.read_bytes()
    if b"\x00" in data[:8000]:
        raise WorkspaceError("fichier binaire : lecture impossible")
    return data.decode("utf-8", errors="replace")


def register_file_tools(registry, workspace: Workspace):
    """Ajoute les outils fichiers au registre."""

    def safe(func):
        """Convertit les erreurs prévues en message lisible pour le modèle."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (WorkspaceError, OSError) as e:
                return f"Erreur : {e}"
        return wrapper

    @registry.tool()
    @safe
    def lister_dossier(chemin: str = ".") -> str:
        """
        Liste le contenu d'un dossier (dossiers puis fichiers, avec tailles).

        Args:
            chemin : Dossier à lister, relatif au dossier de travail ou absolu
        """
        folder = workspace.resolve(chemin)
        if not folder.is_dir():
            return f"Erreur : {chemin} n'est pas un dossier."
        entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines = [f"{workspace.display(folder)} :"]
        for entry in entries[:200]:
            if entry.is_dir():
                lines.append(f"  [dossier] {entry.name}/")
            else:
                lines.append(f"  {entry.name} ({_human_size(entry.stat().st_size)})")
        if len(entries) > 200:
            lines.append(f"  ... et {len(entries) - 200} autres")
        if not entries:
            lines.append("  (vide)")
        return "\n".join(lines)

    @registry.tool()
    @safe
    def lire_fichier(chemin: str, debut: int = 1) -> str:
        """
        Lit un fichier texte (configuration, notes, code, logs...).
        Renvoie au plus 400 lignes à partir de la ligne `debut`.

        Args:
            chemin : Fichier à lire
            debut  : Numéro de la première ligne (1 = début du fichier)
        """
        path = workspace.resolve(chemin)
        if not path.is_file():
            return f"Erreur : fichier introuvable : {chemin}"
        lines = _read_text(path).splitlines()
        start = max(1, debut)
        chunk = lines[start - 1:start - 1 + MAX_LINES]
        header = f"{workspace.display(path)} (lignes {start}-{start + len(chunk) - 1}"
        header += f" sur {len(lines)}) :"
        body = "\n".join(chunk)
        if start - 1 + MAX_LINES < len(lines):
            body += f"\n... suite avec debut={start + MAX_LINES}"
        return f"{header}\n{body}"

    @registry.tool()
    @safe
    def chercher_fichiers(motif: str, dossier: str = ".") -> str:
        """
        Cherche des fichiers par leur nom (motif type *.mkv, *facture*).

        Args:
            motif   : Motif du nom, ex. "*.conf" ou "*vacances*"
            dossier : Dossier de départ
        """
        start = workspace.resolve(dossier)
        pattern = motif if any(c in motif for c in "*?[") else f"*{motif}*"
        found = []
        for path in workspace.walk(start):
            if fnmatch.fnmatch(path.name.lower(), pattern.lower()):
                found.append(workspace.display(path))
                if len(found) >= MAX_RESULTS:
                    break
        note = ("\n(recherche arrêtée au bout de 20 s : précisez le dossier)"
                if workspace.truncated else "")
        if not found:
            return "Aucun fichier trouvé." + note
        suffix = f"\n(limité à {MAX_RESULTS} résultats)" if len(found) >= MAX_RESULTS else ""
        return "\n".join(found) + suffix + note

    @registry.tool()
    @safe
    def chercher_texte(texte: str, dossier: str = ".", motif: str = "*") -> str:
        """
        Cherche un texte à l'intérieur des fichiers (comme grep).

        Args:
            texte   : Texte à chercher (sans tenir compte de la casse)
            dossier : Dossier de départ
            motif   : Filtre sur le nom des fichiers, ex. "*.yml"
        """
        start = workspace.resolve(dossier)
        needle = texte.lower()
        results = []
        for path in workspace.walk(start):
            if not fnmatch.fnmatch(path.name.lower(), motif.lower()):
                continue
            try:
                content = _read_text(path)
            except (WorkspaceError, OSError):
                continue
            for number, line in enumerate(content.splitlines(), 1):
                if needle in line.lower():
                    results.append(f"{workspace.display(path)}:{number}: {line.strip()[:200]}")
                    if len(results) >= MAX_RESULTS:
                        return "\n".join(results) + f"\n(limité à {MAX_RESULTS} résultats)"
        note = ("\n(recherche arrêtée au bout de 20 s : précisez le dossier)"
                if workspace.truncated else "")
        return ("\n".join(results) if results else "Texte introuvable.") + note

    @registry.tool(confirm=True)
    @safe
    def ecrire_fichier(chemin: str, contenu: str, ajouter: bool = False) -> str:
        """
        Écrit un fichier texte (crée les dossiers si besoin). L'utilisateur
        doit confirmer. Écrase le fichier sauf si ajouter=true.

        Args:
            chemin  : Fichier à écrire
            contenu : Texte à écrire
            ajouter : true pour ajouter à la fin au lieu d'écraser
        """
        path = workspace.resolve(chemin)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a" if ajouter else "w", encoding="utf-8") as f:
            f.write(contenu)
        action = "complété" if ajouter else "écrit"
        return f"Fichier {action} : {workspace.display(path)} ({len(contenu)} caractères)"

    return registry
