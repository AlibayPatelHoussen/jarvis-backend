"""
tests/test_builtin_tools.py
===========================
Tests unitaires pour tools/builtin.py
"""

import pytest

from core.memory import LongTermMemory
from tools.builtin import register_builtin_tools
from tools.registry import ToolRegistry


@pytest.fixture
def memory(tmp_path):
    return LongTermMemory(db_path=tmp_path / "m.db")


@pytest.fixture
def tools(memory):
    return register_builtin_tools(ToolRegistry(), memory)


def test_builtin_tool_names(tools):
    assert tools.names() == [
        "actualites", "calculer", "date_heure", "memoriser",
        "meteo", "oublier", "souvenirs",
    ]


def test_memory_tools_need_memory():
    assert "memoriser" not in register_builtin_tools(ToolRegistry())


def test_calculer_accepts_common_symbols(tools):
    assert tools.execute("calculer", {"expression": "(3 * 45) / 60"}) == "(3 * 45) / 60 = 2.25"
    assert tools.execute("calculer", {"expression": "2^10"}) == "2**10 = 1024"
    assert tools.execute("calculer", {"expression": "6 × 7"}) == "6 * 7 = 42"
    assert "Division par zéro" in tools.execute("calculer", {"expression": "1/0"})


def test_date_heure(tools):
    result = tools.execute("date_heure")
    assert "ISO" in result and " h " in result


def test_memory_tools(tools, memory):
    assert tools.execute("souvenirs") == "Aucun fait mémorisé."
    tools.execute("memoriser", {"fait": "j'habite à Montréal"})
    tools.execute("memoriser", {"fait": "j'aime le thé"})
    assert tools.execute("souvenirs") == "- j'habite à Montréal\n- j'aime le thé"
    assert tools.execute("oublier", {"mot_cle": "THÉ"}) == "Oublié : j'aime le thé"
    tools.execute("memoriser", {"fait": "j'ai un chat"})
    assert list(memory.get_all().values()) == ["j'habite à Montréal", "j'ai un chat"]


def test_meteo_and_actualites_use_tools(tools, monkeypatch):
    import tools.builtin as builtin
    seen = {}

    class FakeWeather:
        def get(self, city=None):
            seen["city"] = city
            return "Soleil"

    class FakeNews:
        def detect_category(self, text):
            return "tech"

        def get_headlines(self, category, max_articles):
            seen["category"] = category
            return []

        def format(self, articles, category):
            return f"=== {category} ==="

    monkeypatch.setattr(builtin, "Weather", FakeWeather)
    monkeypatch.setattr(builtin, "News", FakeNews)
    assert tools.execute("meteo", {"ville": "Lyon"}) == "Soleil"
    assert seen["city"] == "Lyon"
    tools.execute("meteo")
    assert seen["city"] is None
    assert tools.execute("actualites", {"categorie": "IA"}) == "=== tech ==="
    assert seen["category"] == "tech"
