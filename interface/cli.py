"""
interface/cli.py
================
Interface en ligne de commande de Jarvis.

Responsabilité unique : lire l'input utilisateur,
envoyer au Brain, afficher la réponse.
"""

from core.brain import Brain
from config import settings
from interface.voice import VoiceOutput, VoiceInput


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
    print("  vocal                    → activer/désactiver le micro")
    print()


def run() -> None:
    """Lance la boucle principale de la CLI."""
    brain = Brain()
    tts = VoiceOutput()
    stt = VoiceInput()

    if not brain.is_ready():
        print()
        print("  ERREUR : Ollama n'est pas accessible.")
        print("  Lancez Ollama et réessayez.")
        print()
        return

    print_welcome()

    # Afficher le statut voix
    if tts.is_available:
        print("  🔊 Synthèse vocale : active")
    if stt.is_available:
        print("  🎤 Reconnaissance vocale : active (tapez 'vocal' pour activer)")
    print()

    voice_mode = False

    while True:
        try:
            # Mode vocal ou texte
            if voice_mode and stt.is_available:
                print("  🎤 Parlez...")
                user_input = stt.listen(timeout=10)
                if user_input:
                    print(f"{settings.USER_NAME} >>> {user_input}")
                else:
                    print("  (pas de son détecté — retour au mode texte)")
                    voice_mode = False
                    continue
            else:
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

        # Activer/désactiver le mode vocal
        if user_input.lower() == "vocal":
            voice_mode = not voice_mode
            status = "activé" if voice_mode else "désactivé"
            print(f"  🎤 Mode vocal {status}")
            continue

        print()
        response = brain.process(user_input)
        print(f"Jarvis >>> {response}")
        print()

        # Réponse vocale
        if tts.is_available:
            tts.speak(response)
