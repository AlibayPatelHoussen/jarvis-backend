"""
tests/test_brain.py
===================
Tests unitaires pour core/brain.py
"""

import tempfile
from pathlib import Path
import pytest
from core.brain import Brain
from core.memory import LongTermMemory


@pytest.fixture
def brain():
    """
    Crée un Brain avec une base SQLite temporaire.
    Chaque test repart d'une base vide.
    """
    tmp = tempfile.mktemp(suffix=".db")
    b = Brain()
    b.long_term = LongTermMemory(db_path=Path(tmp))
    return b


def test_brain_can_be_created(brain):
    assert brain is not None


def test_brain_has_llm(brain):
    assert brain.llm is not None


def test_process_empty_message(brain):
    assert brain.process("") == ""


def test_process_whitespace_message(brain):
    assert brain.process("   ") == ""


def test_remember_command(brain):
    response = brain.process("souviens-toi que je suis développeur")
    assert "développeur" in response.lower()
    assert brain.long_term.count() > 0


def test_recall_command(brain):
    brain.long_term.save("test_key", "je suis développeur")
    response = brain.process("que sais-tu de moi ?")
    assert "développeur" in response.lower()


def test_recall_empty(brain):
    response = brain.process("que sais-tu de moi ?")
    assert "rien" in response.lower()


def test_clear_command(brain):
    brain.short_term.add("user", "test")
    brain.short_term.add("assistant", "réponse")
    response = brain.process("nouvelle conversation")
    assert brain.short_term.count() == 0
    assert "effacée" in response.lower()


def test_forget_command(brain):
    brain.long_term.save("k1", "je suis développeur")
    response = brain.process("oublie développeur")
    assert "développeur" in response.lower()
    assert brain.long_term.count() == 0


@pytest.mark.integration
def test_brain_is_ready(brain):
    assert brain.is_ready() is True


@pytest.mark.integration
def test_process_returns_string(brain):
    response = brain.process("Réponds juste 'ok'.")
    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.integration
def test_process_responds_in_french(brain):
    response = brain.process("Quelle est ta langue principale ?")
    french_words = ["français", "france", "je", "est", "pour", "dans"]
    assert any(word in response.lower() for word in french_words)


# ─────────────────────────────────────────────
# Non-régression : ordre des commandes
# ─────────────────────────────────────────────

def test_oublie_tout_clears_conversation_not_facts(brain):
    brain.long_term.save("k1", "tout va bien")
    brain.short_term.add("user", "test")
    brain.short_term.add("assistant", "réponse")
    response = brain.process("oublie tout")
    assert "effacée" in response.lower()
    assert brain.short_term.count() == 0
    assert brain.long_term.count() == 1


def test_efface_la_conversation_clears_conversation(brain):
    brain.short_term.add("user", "test")
    response = brain.process("Efface la conversation !")
    assert "effacée" in response.lower()
    assert brain.short_term.count() == 0


# ─────────────────────────────────────────────
# Non-régression : faux positifs
# ─────────────────────────────────────────────

@pytest.mark.parametrize("message", [
    "Je recommence le projet demain, des conseils ?",
    "Est-ce que je supprime ce fichier ?",
    "Comment dire « je n'oublie jamais » en anglais ?",
    "Je note que tu es lent aujourd'hui",
    "Explique-moi ce que tu sais de moi et des autres",
])
def test_normal_sentences_are_not_memory_commands(brain, message):
    assert brain._handle_memory_commands(message) is None


@pytest.mark.parametrize("message", [
    "Que sais-tu de moi ?",
    "qu'est-ce que tu sais de moi",
    "Dis-moi ce que tu sais de moi.",
])
def test_recall_variants(brain, message):
    brain.long_term.save("k1", "je suis développeur")
    assert "développeur" in brain.process(message)


def test_commands_are_case_insensitive(brain):
    brain.process("SOUVIENS-TOI QUE j'aime le café")
    assert brain.long_term.count() == 1
    brain.process("Oublie café")
    assert brain.long_term.count() == 0


# ─────────────────────────────────────────────
# Non-régression : casse et ponctuation des faits
# ─────────────────────────────────────────────

def test_remember_keeps_original_case(brain):
    response = brain.process("Souviens-toi que j'habite à Montréal")
    assert "Montréal" in response
    assert "j'habite à Montréal" in brain.long_term.get_all().values()


def test_remember_strips_trailing_punctuation(brain):
    response = brain.process("Retiens que je bois du thé.")
    assert response == "Noté ! Je me souviendrai que je bois du thé."
    assert "je bois du thé" in brain.long_term.get_all().values()


def test_forget_strips_trailing_punctuation(brain):
    brain.long_term.save("k1", "j'aime le café")
    brain.process("oublie café !")
    assert brain.long_term.count() == 0


# ─────────────────────────────────────────────
# Non-régression : clés des faits
# ─────────────────────────────────────────────

def test_remember_after_delete_does_not_overwrite(brain):
    brain.process("souviens-toi que a")
    brain.process("souviens-toi que b")
    brain.process("oublie a")
    brain.process("souviens-toi que c")
    assert sorted(brain.long_term.get_all().values()) == ["b", "c"]


def test_remember_ignores_non_numeric_keys(brain):
    brain.long_term.save("prenom", "Houssen")
    brain.long_term.save("fact_7", "x")
    brain.process("souviens-toi que y")
    assert brain.long_term.get("fact_8") == "y"
    assert brain.long_term.count() == 3


# ─────────────────────────────────────────────
# Non-régression : routage des outils
# ─────────────────────────────────────────────

@pytest.fixture
def routed(brain):
    """Brain dont les outils réseau sont remplacés par des espions."""
    brain._get_weather = lambda city=None: f"WEATHER:{city}"
    brain._get_news = lambda hint="": f"NEWS:{hint}"
    return brain


@pytest.mark.parametrize("message", [
    "J'ai des nouvelles de ma mère",
    "Quelle température pour cuire un poulet ?",
    "J'ai un calcul rénal",
    "Le résultat du match ?",
    "J'écris mon journal intime",
    "Tu connais les news de Bloomberg ?",
    "Résous ce problème de logique",
    "La météorologie, c'est quoi ?",
])
def test_normal_sentences_do_not_trigger_tools(routed, message):
    assert routed._handle_memory_commands(message) is None


@pytest.mark.parametrize("message, expected", [
    ("météo", "WEATHER:None"),
    ("Météo à Paris ?", "WEATHER:Paris"),
    ("Quel temps fait-il à Montréal", "WEATHER:Montréal"),
    ("température à New York !", "WEATHER:New York"),
    ("actualités", "NEWS:"),
    ("Actualités tech ?", "NEWS:tech"),
    ("les news sport", "NEWS:sport"),
    ("quoi de neuf", "NEWS:"),
    ("Les titres du jour", "NEWS:"),
])
def test_tool_commands_are_routed(routed, message, expected):
    assert routed._handle_memory_commands(message) == expected


@pytest.mark.parametrize("message, expected", [
    ("calcule 15 * 7", "15 * 7 = 105"),
    ("Combien fait 2+2 ?", "2+2 = 4"),
    ("calcul (2 + 3) * 4.", "(2 + 3) * 4 = 20"),
])
def test_calc_commands(brain, message, expected):
    assert brain.process(message) == expected
