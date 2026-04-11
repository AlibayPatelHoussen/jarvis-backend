"""
interface/cli.py
================
Interface en ligne de commande de Jarvis.

Responsabilité unique : lire l'input utilisateur,
envoyer au Brain, afficher la réponse.
"""

from core.brain import Brain
from config import settings


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
    """Affiche l'aide complète avec les commandes mémoire."""
    print()
    print_separator()
    print("  COMMANDES DISPONIBLES")
    print_separator()
    print()
    print("  CONVERSATION")
    print("  Parlez naturellement — Jarvis répond en français")
    print()
    print("  MÉMOIRE")
    print("  souviens-toi que [info]  → mémoriser un fait")
    print("  que sais-tu de moi ?     → voir les faits connus")
    print("  oublie [mot]             → oublier un fait")
    print("  nouvelle conversation    → effacer l'historique")
    print()
    print("  SYSTÈME")
    print("  aide                     → afficher cette aide")
    print("  quit / exit              → quitter Jarvis")
    print_separator()
    print("  CALCUL")
    print("  calcule [expression]     → ex: calcule 15 * 7")
    print("  combien fait [expr]      → ex: combien fait 2 ** 10")
    print("  MÉTÉO")
    print("  météo                    → météo à votre position")
    print("  météo à [ville]          → météo d'une ville")
    print("  ACTUALITÉS")
    print("  actualités               → titres du moment")
    print("  actualités tech          → actualités tech")
    print("  actualités sport         → actualités sport")
    print()


def run() -> None:
    """Lance la boucle principale de la CLI."""
    brain = Brain()

    if not brain.is_ready():
        print()
        print("  ERREUR : Ollama n'est pas accessible.")
        print("  Lancez Ollama et réessayez.")
        print()
        return

    print_welcome()

    while True:
        try:
            user_input = input(f"{settings.USER_NAME} >>> ").strip()

        except KeyboardInterrupt:
            print()
            print()
            print("  Au revoir !")
            print()
            break

        except EOFError:
            break

        if not user_input:
            continue

        if user_input.lower() in QUIT_COMMANDS:
            print()
            print(f"  Au revoir {settings.USER_NAME} !")
            print()
            break

        if user_input.lower() == HELP_COMMAND:
            print_help()
            continue

        print()
        response = brain.process(user_input)
        print(f"Jarvis >>> {response}")
        print()
