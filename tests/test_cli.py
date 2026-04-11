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
