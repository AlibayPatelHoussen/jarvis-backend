"""
tests/test_files.py
===================
Tests unitaires pour tools/files.py
"""

import os

import pytest

from tools.files import Workspace, WorkspaceError, register_file_tools
from tools.registry import ToolRegistry


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "travail"
    (root / "Films").mkdir(parents=True)
    (root / "Films" / "Vacances 2024.mkv").write_bytes(b"\x00" * 10)
    (root / "Films" / "notes.txt").write_text("Revoir Inception\nFinir la série\n")
    (root / "docker-compose.yml").write_text("services:\n  jellyfin:\n    image: jellyfin\n")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("jellyfin secret")
    (tmp_path / "secret.txt").write_text("hors du dossier")
    return Workspace(root)


@pytest.fixture
def tools(ws):
    return register_file_tools(ToolRegistry(), ws)


@pytest.mark.parametrize("path", ["..", "../secret.txt", "/etc/passwd", "Films/../../secret.txt"])
def test_workspace_blocks_paths_outside(ws, path):
    with pytest.raises(WorkspaceError):
        ws.resolve(path)


def test_workspace_blocks_symlink_escape(ws, tmp_path):
    link = ws.root / "lien"
    try:
        os.symlink(tmp_path / "secret.txt", link)
    except (OSError, NotImplementedError):
        pytest.skip("liens symboliques non disponibles")
    with pytest.raises(WorkspaceError):
        ws.resolve("lien")


def test_workspace_accepts_inside_paths(ws):
    assert ws.resolve() == ws.root
    assert ws.resolve("Films/notes.txt") == ws.root / "Films" / "notes.txt"
    assert ws.resolve(str(ws.root / "Films")) == ws.root / "Films"


def test_schemas_are_typed(tools):
    params = tools.get("ecrire_fichier").parameters
    assert params["properties"]["ajouter"]["type"] == "boolean"
    assert params["required"] == ["chemin", "contenu"]
    assert tools.get("ecrire_fichier").confirm is True


def test_lister_dossier(tools):
    out = tools.execute("lister_dossier")
    assert "[dossier] Films/" in out and "docker-compose.yml" in out
    assert "Erreur : accès refusé" in tools.execute("lister_dossier", {"chemin": ".."})


def test_lire_fichier(tools):
    out = tools.execute("lire_fichier", {"chemin": "Films/notes.txt"})
    assert "(lignes 1-2 sur 2)" in out and "Revoir Inception" in out
    assert "Finir la série" in tools.execute("lire_fichier", {"chemin": "Films/notes.txt",
                                                              "debut": 2})
    assert "binaire" in tools.execute("lire_fichier", {"chemin": "Films/Vacances 2024.mkv"})
    assert "introuvable" in tools.execute("lire_fichier", {"chemin": "absent.txt"})
    assert "accès refusé" in tools.execute("lire_fichier", {"chemin": "../secret.txt"})


def test_lire_fichier_pagination(tools, ws):
    (ws.root / "long.log").write_text("\n".join(f"ligne {i}" for i in range(1, 1001)))
    out = tools.execute("lire_fichier", {"chemin": "long.log"})
    assert "(lignes 1-400 sur 1000)" in out and "suite avec debut=401" in out


def test_chercher_fichiers(tools):
    assert tools.execute("chercher_fichiers", {"motif": "*.mkv"}) == "Films/Vacances 2024.mkv"
    assert tools.execute("chercher_fichiers", {"motif": "vacances"}) == "Films/Vacances 2024.mkv"
    assert tools.execute("chercher_fichiers", {"motif": "*.iso"}) == "Aucun fichier trouvé."


def test_chercher_texte_skips_git_and_binaries(tools):
    out = tools.execute("chercher_texte", {"texte": "JELLYFIN"})
    assert out.splitlines() == [
        "docker-compose.yml:2: jellyfin:",
        "docker-compose.yml:3: image: jellyfin",
    ]
    assert tools.execute("chercher_texte", {"texte": "série", "motif": "*.yml"}) \
        == "Texte introuvable."


def test_ecrire_fichier(tools, ws):
    assert tools.execute("ecrire_fichier", {"chemin": "a.txt", "contenu": "x"}) \
        == "Action refusée par l'utilisateur."
    ok = lambda s: True  # noqa: E731
    out = tools.execute("ecrire_fichier", {"chemin": "Nouveau/a.txt", "contenu": "Bonjour"},
                        confirm=ok)
    assert out == "Fichier écrit : Nouveau/a.txt (7 caractères)"
    tools.execute("ecrire_fichier", {"chemin": "Nouveau/a.txt", "contenu": " !",
                                     "ajouter": True}, confirm=ok)
    assert (ws.root / "Nouveau" / "a.txt").read_text() == "Bonjour !"
    assert "accès refusé" in tools.execute(
        "ecrire_fichier", {"chemin": "../pirate.txt", "contenu": "x"}, confirm=ok)


# ─────────────────────────────────────────────
# Dossier de travail « / » (accès complet)
# ─────────────────────────────────────────────

def test_root_workspace_accepts_any_path(tmp_path):
    ws = Workspace("/")
    assert ws.resolve(str(tmp_path)) == tmp_path.resolve()
    assert ws.resolve("etc") == Workspace("/").root / "etc"


def test_walk_skips_virtual_filesystems():
    ws = Workspace("/")
    seen = set()
    for path in ws.walk(Workspace("/").root, seconds=0.5):
        seen.add(str(path).split("/")[1])
    assert not seen & {"proc", "sys", "dev", "run"}


def test_search_stops_after_time_limit(tools, ws, monkeypatch):
    import tools.files as files
    monkeypatch.setattr(files, "SEARCH_SECONDS", 0)
    monkeypatch.setattr(files.Workspace.walk, "__defaults__", (0,))
    out = tools.execute("chercher_fichiers", {"motif": "*.iso"})
    assert "arrêtée au bout de 20 s" in out


# ─────────────────────────────────────────────
# Renommer, créer, supprimer
# ─────────────────────────────────────────────

def rename(tools, chemin, nouveau):
    return tools.execute("renommer_fichier", {"chemin": chemin, "nouveau": nouveau})


def test_rename_in_place_and_move(tools, ws):
    assert rename(tools, "Films/notes.txt", "a-voir.txt") \
        == "Renommé : Films/notes.txt → Films/a-voir.txt"
    assert (ws.root / "Films" / "a-voir.txt").exists()
    assert "le dossier Archives n'existe pas" in rename(tools, "Films/a-voir.txt",
                                                        "Archives/a-voir.txt")
    tools.execute("creer_dossier", {"chemin": "Archives"})
    assert rename(tools, "Films/a-voir.txt", "Archives/a-voir.txt").endswith(
        "→ Archives/a-voir.txt")


def test_rename_never_overwrites_or_escapes(tools, ws):
    (ws.root / "b.txt").write_text("b")
    (ws.root / "c.txt").write_text("c")
    assert "existe déjà" in rename(tools, "b.txt", "c.txt")
    assert (ws.root / "c.txt").read_text() == "c"
    assert "accès refusé" in rename(tools, "b.txt", "../../b.txt")
    assert "introuvable" in rename(tools, "absent", "x")
    assert "dossier de travail" in rename(tools, ".", "x")


def test_delete_needs_confirmation(tools, ws):
    def delete(chemin, **kw):
        return tools.execute("supprimer_fichier", {"chemin": chemin}, **kw)

    ok = lambda s: True  # noqa: E731
    assert tools.get("supprimer_fichier").confirm is True
    assert tools.get("renommer_fichier").confirm is False
    assert delete("Films") == "Action refusée par l'utilisateur."
    assert (ws.root / "Films").exists()
    assert delete("Films", confirm=ok) == "Dossier supprimé : Films (2 fichier(s))"
    assert not (ws.root / "Films").exists()
    assert delete("docker-compose.yml", confirm=ok) == "Fichier supprimé : docker-compose.yml"
    assert "refus" in delete(".", confirm=ok)
    assert "accès refusé" in delete("../secret.txt", confirm=ok)
