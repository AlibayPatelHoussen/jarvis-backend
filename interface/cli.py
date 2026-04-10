"""
interface/cli.py
================
Interface en ligne de commande de Jarvis.

Responsabilité unique : lire l'input utilisateur,
envoyer au Brain, afficher la réponse.

La CLI ne contient aucune logique métier.
Elle ne sait pas comment Ollama fonctionne.
Elle parle uniquement au Brain.
"""

from core.brain import Brain
from config import settings


# Commandes spéciales reconnues par la CLI
# Le Brain n'a pas besoin de les voir
QUIT_COMMANDS = {"quit", "exit", "q", "au revoir", "bye"}
HELP_COMMAND = "aide"


def print_separator() -> None:
    """Affiche une ligne de séparation."""
    print("-" * 50)


def print_welcome() -> None:
    """Affiche le message de bienvenue."""
    print_separator()
    print("  JARVIS — Assistant IA Personnel")
    print(f"  Bonjour {settings.USER_NAME} !")
    print(f"  Modèle : {settings.OLLAMA_MODEL}")
    print()
    print("  Tapez 'aide' pour la liste des commandes")
    print("  Tapez 'quit' pour quitter")
    print_separator()
    print()


def print_help() -> None:
    """Affiche l'aide."""
    print()
    print("  COMMANDES DISPONIBLES :")
    print("  aide          → afficher cette aide")
    print("  quit / exit   → quitter Jarvis")
    print()
    print("  Pour tout le reste, parlez naturellement !")
    print()


def run() -> None:
    """
    Lance la boucle principale de la CLI.

    C'est la fonction principale — elle tourne
    jusqu'à ce que l'utilisateur tape 'quit'.
    """
    # Initialiser le Brain
    brain = Brain()

    # Vérifier qu'Ollama est disponible
    if not brain.is_ready():
        print()
        print("  ERREUR : Ollama n'est pas accessible.")
        print("  Lancez Ollama et réessayez.")
        print()
        return

    # Afficher le message de bienvenue
    print_welcome()

    # Boucle principale
    while True:
        try:
            # Lire l'input utilisateur
            user_input = input(f"{settings.USER_NAME} >>> ").strip()

        except KeyboardInterrupt:
            # Ctrl+C — quitter proprement
            print()
            print()
            print("  Au revoir !")
            print()
            break

        except EOFError:
            # Ctrl+D — quitter proprement
            break

        # Ignorer les lignes vides
        if not user_input:
            continue

        # Commandes spéciales
        if user_input.lower() in QUIT_COMMANDS:
            print()
            print(f"  Au revoir {settings.USER_NAME} !")
            print()
            break

        if user_input.lower() == HELP_COMMAND:
            print_help()
            continue

        # Envoyer au Brain et afficher la réponse
        print()
        response = brain.process(user_input)
        print(f"Jarvis >>> {response}")
        print()
