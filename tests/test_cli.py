"""
tests/test_cli.py
=================
Tests unitaires pour interface/cli.py
"""

from interface.cli import (
    QUIT_COMMANDS,
    HELP_COMMAND,
    print_separator,
    print_welcome,
    print_help,
)


def test_quit_commands_not_empty():
    """La liste des commandes de sortie ne doit pas être vide."""
    assert len(QUIT_COMMANDS) > 0


def test_quit_commands_contains_quit():
    """'quit' doit être une commande de sortie."""
    assert "quit" in QUIT_COMMANDS


def test_quit_commands_contains_exit():
    """'exit' doit être une commande de sortie."""
    assert "exit" in QUIT_COMMANDS


def test_help_command_defined():
    """La commande d'aide doit être définie."""
    assert HELP_COMMAND == "aide"


def test_print_separator_runs(capsys):
    """print_separator() doit afficher quelque chose."""
    print_separator()
    captured = capsys.readouterr()
    assert len(captured.out) > 0


def test_print_welcome_contains_jarvis(capsys):
    """Le message de bienvenue doit mentionner Jarvis."""
    print_welcome()
    captured = capsys.readouterr()
    assert "JARVIS" in captured.out


def test_print_help_contains_quit(capsys):
    """L'aide doit mentionner la commande quit."""
    print_help()
    captured = capsys.readouterr()
    assert "quit" in captured.out


def test_print_help_contains_aide(capsys):
    """L'aide doit mentionner la commande aide."""
    print_help()
    captured = capsys.readouterr()
    assert "aide" in captured.out


def test_print_help_contains_memory_commands(capsys):
    """L'aide doit mentionner les commandes mémoire."""
    print_help()
    captured = capsys.readouterr()
    assert "souviens-toi" in captured.out
    assert "que sais-tu" in captured.out
    assert "oublie" in captured.out


def test_print_help_contains_nouvelle_conversation(capsys):
    """L'aide doit mentionner 'nouvelle conversation'."""
    print_help()
    captured = capsys.readouterr()
    assert "nouvelle conversation" in captured.out


# ─────────────────────────────────────────────
# Non-régression : démarrage sans Ollama
# ─────────────────────────────────────────────

def test_run_works_without_ollama(monkeypatch, capsys, tmp_path):
    from interface import cli
    from tools.tasks import TaskStore

    class FakeBrain:
        tasks = TaskStore(tmp_path / "t.db")

        def health(self):
            return "Ollama n'est pas accessible sur http://localhost:11434."

        def process(self, message, on_token=None):
            return f"echo:{message}"

    class FakeVoice:
        is_available = False
        stopped = False

        def shutdown(self):
            FakeVoice.stopped = True

    inputs = iter(["calcule 1 + 1", "quit"])
    monkeypatch.setattr(cli, "Brain", FakeBrain)
    monkeypatch.setattr(cli, "VoiceOutput", FakeVoice)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    cli.run()
    out = capsys.readouterr().out
    assert "Ollama n'est pas accessible" in out
    assert "echo:calcule 1 + 1" in out
    assert FakeVoice.stopped


def test_help_sections_are_separated(capsys):
    from interface.cli import print_help
    print_help()
    out = capsys.readouterr().out
    for section in ["CALCUL", "MÉTÉO", "ACTUALITÉS", "SYSTÈME"]:
        assert f"\n\n  {section}" in out


# ─────────────────────────────────────────────
# Étape 1 : streaming et commandes /xxx
# ─────────────────────────────────────────────

class FakeVoice:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.said = []

    def say(self, text):
        if self.enabled:
            self.said.append(text)

    def shutdown(self):
        pass


def _run_loop(monkeypatch, brain, lines):
    from interface import cli
    inputs = iter(lines + ["quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    voice = FakeVoice(enabled=True)
    cli._loop(brain, voice)
    return voice


def test_loop_streams_llm_answer_once(monkeypatch, capsys):
    class StreamingBrain:
        def process(self, message, on_token=None):
            for piece in ["Bon", "jour"]:
                on_token(piece)
            return "Bonjour"

    voice = _run_loop(monkeypatch, StreamingBrain(), ["Salut"])
    out = capsys.readouterr().out
    assert out.count("Bonjour") == 1
    assert "Jarvis >>> Bonjour" in out
    assert voice.said == ["Bonjour"]


def test_loop_prints_direct_command_answer(monkeypatch, capsys):
    class DirectBrain:
        def process(self, message, on_token=None):
            return "2 + 2 = 4"

    _run_loop(monkeypatch, DirectBrain(), ["calcule 2 + 2"])
    assert "Jarvis >>> 2 + 2 = 4" in capsys.readouterr().out


def test_slash_commands(monkeypatch, capsys):
    from interface import cli

    class Llm:
        model = "mistral"

        def get_models(self):
            return ["mistral:latest", "qwen2.5:7b"]

    class SlashBrain:
        llm = Llm()
        cleared = False

        def health(self):
            return None

        def clear_conversation(self):
            SlashBrain.cleared = True

        def process(self, message, on_token=None):
            raise AssertionError("une commande /xxx ne doit pas aller au Brain")

    brain = SlashBrain()
    voice = FakeVoice(enabled=True)
    for command in ["/modele", "/modele qwen2.5:7b", "/voix off", "/effacer", "/inconnue"]:
        assert cli._handle_slash_command(command, brain, voice) is True
    out = capsys.readouterr().out
    assert "qwen2.5:7b" in out
    assert brain.llm.model == "qwen2.5:7b"
    assert voice.enabled is False
    assert SlashBrain.cleared
    assert "Commande inconnue" in out
    assert cli._handle_slash_command("bonjour", brain, voice) is False


def test_voice_is_created_lazily(monkeypatch):
    from interface import cli
    created = []
    monkeypatch.setattr(cli, "VoiceOutput", lambda: created.append(1))
    voice = cli.Voice(enabled=False)
    voice.say("test")
    voice.shutdown()
    assert created == []


def test_loop_shows_tool_calls_on_their_own_line(monkeypatch, capsys):
    class ToolBrain:
        def process(self, message, on_token=None):
            on_token("Je calcule.")
            self.on_tool("calculer", {"expression": "2+2"})
            on_token("2+2 = 4")
            return "Je calcule.2+2 = 4"

    _run_loop(monkeypatch, ToolBrain(), ["combien ?"])
    out = capsys.readouterr().out
    assert "Jarvis >>> Je calcule.\n  [outil] calculer(expression='2+2')\nJarvis >>> 2+2 = 4" in out


def test_confirm(monkeypatch):
    from interface import cli
    answers = iter(["o", "non"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert cli._confirm("supprimer('a')") is True
    assert cli._confirm("supprimer('a')") is False


def test_notify_shows_late_reminders(capsys):
    from datetime import datetime, timedelta
    from interface import cli
    from tools.tasks import Reminder
    voice = FakeVoice(enabled=True)
    cli._notify(Reminder(1, "Appeler maman", datetime.now()), voice)
    cli._notify(Reminder(2, "Poubelles", datetime.now() - timedelta(hours=1)), voice,
                reprint_prompt=False)
    out = capsys.readouterr().out
    assert "*** RAPPEL : Appeler maman ***" in out
    assert "*** RAPPEL : Poubelles (prévu aujourd'hui" in out or "(prévu hier" in out \
        or "*** RAPPEL : Poubelles (prévu" in out
    assert voice.said == ["Rappel : Appeler maman", "Rappel : Poubelles"]
