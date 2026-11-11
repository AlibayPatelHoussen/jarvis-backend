"""
interface/cli.py
================
Interface en ligne de commande de Jarvis.

Responsabilité unique : lire l'input utilisateur,
envoyer au Brain, afficher la réponse (en direct).
"""

from core.brain import Brain
from config import settings
from interface.voice import VoiceOutput

try:  # Flèches haut/bas pour rappeler les messages précédents
    import readline  # noqa: F401
except ImportError:  # Windows sans pyreadline3
    pass


QUIT_COMMANDS = {"quit", "exit", "q", "au revoir", "bye", "/quitter", "/quit"}
HELP_COMMAND = "aide"
HELP_COMMANDS = {HELP_COMMAND, "/aide", "/help", "?"}


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
    """Affiche l'aide complète."""
    print()
    print_separator()
    print("  COMMANDES DISPONIBLES")
    print_separator()
    print()
    print("  CONVERSATION")
    print("  Parlez naturellement — Jarvis répond en direct")
    print()
    print("  MÉMOIRE")
    print("  souviens-toi que [info]  → mémoriser un fait")
    print("  que sais-tu de moi ?     → voir les faits connus")
    print("  oublie [mot]             → oublier un fait")
    print("  nouvelle conversation    → effacer l'historique")
    print()
    print("  CALCUL")
    print("  calcule [expression]     → ex: calcule 15 * 7")
    print("  combien fait [expr]      → ex: combien fait 2 ** 10")
    print()
    print("  MÉTÉO")
    print("  météo                    → météo à votre position")
    print("  météo à [ville]          → météo d'une ville")
    print()
    print("  ACTUALITÉS")
    print("  actualités               → titres du moment")
    print("  actualités tech          → actualités tech")
    print("  actualités sport         → actualités sport")
    print()
    print("  SYSTÈME")
    print("  /aide                    → afficher cette aide")
    print("  /modele [nom]            → voir ou changer de modèle")
    print("  /voix on|off             → activer ou couper la voix")
    print("  /effacer                 → effacer la conversation")
    print("  quit / exit              → quitter Jarvis")
    print_separator()
    print()


def run() -> None:
    """Lance la boucle principale de la CLI."""
    brain = Brain()
    # La voix est optionnelle et créée seulement si elle est activée
    voice = Voice(settings.VOICE_ENABLED)

    print_welcome()

    # Sans Ollama, la mémoire, le calcul, la météo et les actualités
    # fonctionnent quand même : on prévient au lieu de quitter.
    warning = brain.health()
    if warning:
        print(f"  ATTENTION : {warning}")
        print("  En attendant, les commandes (aide, calcul, météo,")
        print("  actualités, mémoire) fonctionnent.")
        print()

    try:
        _loop(brain, voice)
    finally:
        # Laisser Jarvis finir sa phrase avant de quitter
        voice.shutdown()


class Voice:
    """Synthèse vocale activable, créée seulement quand on l'utilise."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._tts = None

    @property
    def tts(self) -> VoiceOutput:
        if self._tts is None:
            self._tts = VoiceOutput()
        return self._tts

    def say(self, text: str) -> None:
        if self.enabled and self.tts.is_available:
            self.tts.speak_async(text)

    def shutdown(self) -> None:
        if self._tts is not None:
            self._tts.shutdown()


def _handle_slash_command(text: str, brain: Brain, voice: Voice) -> bool:
    """
    Traite les commandes /xxx.

    Returns:
        True si le texte était une commande système (déjà traitée).
    """
    if not text.startswith("/"):
        return False
    name, _, arg = text[1:].partition(" ")
    name, arg = name.lower(), arg.strip()

    if name in ("modele", "modèle", "model"):
        if arg:
            brain.llm.model = arg
            print(f"  Modèle changé : {arg}")
            warning = brain.health()
            if warning:
                print(f"  ATTENTION : {warning}")
        else:
            print(f"  Modèle actuel : {brain.llm.model}")
            models = brain.llm.get_models()
            if models:
                print(f"  Installés     : {', '.join(models)}")
    elif name == "voix":
        if arg in ("on", "off"):
            voice.enabled = arg == "on"
        state = "activée" if voice.enabled else "coupée"
        if voice.enabled and not voice.tts.is_available:
            state += " (mais pyttsx3 n'est pas disponible)"
        print(f"  Voix {state}.")
    elif name in ("effacer", "clear", "nouveau"):
        brain.clear_conversation()
        print("  Conversation effacée.")
    else:
        print(f"  Commande inconnue : /{name} — tapez /aide")
    print()
    return True


def _loop(brain: Brain, voice: Voice) -> None:
    """Boucle de lecture des messages."""

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

        if user_input.lower() in HELP_COMMANDS:
            print_help()
            continue

        if _handle_slash_command(user_input, brain, voice):
            continue

        print()
        print("Jarvis >>> ", end="", flush=True)
        streamed = []

        def on_token(token: str) -> None:
            streamed.append(token)
            print(token, end="", flush=True)

        try:
            response = brain.process(user_input, on_token=on_token)
        except KeyboardInterrupt:
            # Ctrl+C pendant une réponse : on l'interrompt sans quitter
            print("\n  (réponse interrompue)")
            print()
            continue

        if not streamed:
            # Commande directe : rien n'a été streamé, on affiche tout
            print(response, end="")
        print()

        # Dire la réponse à voix haute si disponible
        voice.say(response)
        print()
