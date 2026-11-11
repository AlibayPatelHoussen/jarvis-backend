"""
tests/test_registry.py
======================
Tests unitaires pour tools/registry.py
"""

import json

import pytest

from tools.registry import Tool, ToolRegistry


@pytest.fixture
def registry():
    reg = ToolRegistry()

    @reg.tool()
    def ajouter(a: int, b: int = 0) -> int:
        """
        Additionne deux nombres.

        Args:
            a : Premier nombre
            b (int): Second nombre,
                sur deux lignes

        Returns:
            La somme
        """
        return a + b

    @reg.tool(name="profil")
    def get_profile(nom: str, actif: bool = True, score: float = 1.5) -> dict:
        """Retourne un profil."""
        return {"nom": nom, "actif": actif, "score": score}

    @reg.tool(confirm=True)
    def supprimer(chemin: str) -> str:
        """Supprime un fichier."""
        return f"supprimé {chemin}"

    @reg.tool()
    def casser() -> str:
        """Lève toujours une erreur."""
        raise RuntimeError("panne")

    return reg


def test_schema_is_inferred_from_signature_and_docstring(registry):
    schema = registry.get("ajouter").schema()
    fn = schema["function"]
    assert schema["type"] == "function"
    assert fn["name"] == "ajouter"
    assert fn["description"] == "Additionne deux nombres."
    assert fn["parameters"] == {
        "type": "object",
        "properties": {
            "a": {"type": "integer", "description": "Premier nombre"},
            "b": {"type": "integer", "description": "Second nombre, sur deux lignes"},
        },
        "required": ["a"],
    }


def test_types_and_custom_name(registry):
    props = registry.get("profil").parameters["properties"]
    assert props == {
        "nom": {"type": "string"},
        "actif": {"type": "boolean"},
        "score": {"type": "number"},
    }
    assert "get_profile" not in registry


def test_names_and_schemas_sorted(registry):
    assert registry.names() == ["ajouter", "casser", "profil", "supprimer"]
    assert [s["function"]["name"] for s in registry.schemas()] == registry.names()
    assert "- ajouter : Additionne deux nombres." in registry.describe()


def test_execute_ok(registry):
    assert registry.execute("ajouter", {"a": 2, "b": 3}) == "5"


def test_execute_returns_json_for_dict(registry):
    assert json.loads(registry.execute("profil", {"nom": "Léa"})) == {
        "nom": "Léa", "actif": True, "score": 1.5,
    }


def test_execute_unknown_tool(registry):
    result = registry.execute("voler", {})
    assert "n'existe pas" in result and "ajouter" in result


def test_execute_missing_argument(registry):
    assert "manquant" in registry.execute("ajouter", {"b": 1})


def test_execute_ignores_invented_arguments(registry):
    assert registry.execute("ajouter", {"a": 1, "c": 99}) == "1"


def test_execute_coerces_simple_types(registry):
    assert registry.execute("ajouter", {"a": "2", "b": "3"}) == "5"
    result = json.loads(registry.execute("profil", {"nom": 42, "actif": "oui", "score": "2,5"}))
    assert result == {"nom": "42", "actif": True, "score": 2.5}
    assert "type integer" in registry.execute("ajouter", {"a": "deux"})


def test_execute_catches_exceptions(registry):
    assert registry.execute("casser") == "Erreur pendant 'casser' : panne"


def test_confirmation(registry):
    asked = []
    assert registry.execute("supprimer", {"chemin": "a.txt"}) == "Action refusée par l'utilisateur."
    assert registry.execute(
        "supprimer", {"chemin": "a.txt"}, confirm=lambda s: asked.append(s) or False
    ) == "Action refusée par l'utilisateur."
    assert asked == ["supprimer(chemin='a.txt')"]
    assert registry.execute(
        "supprimer", {"chemin": "a.txt"}, confirm=lambda s: True
    ) == "supprimé a.txt"


def test_invalid_name_rejected():
    with pytest.raises(ValueError):
        ToolRegistry().register(Tool(name="nom avec espaces", description="x", func=print))


def test_unregister(registry):
    registry.unregister("casser")
    assert "casser" not in registry
    assert len(registry) == 3
