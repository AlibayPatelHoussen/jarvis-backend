"""
interface/cli.py
================
Interface en ligne de commande de Jarvis.

Responsabilité unique : lire l'input utilisateur,
envoyer au Brain, afficher la réponse (en direct).
"""

from datetime import datetime, timedelta

from core.brain import Brain
from config import settings
from interface.voice import VoiceOutput
from tools.tasks import Reminder, ReminderScheduler, format_when

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
    print("  TÂCHES, RAPPELS, NOTES")
    print("  mes tâches / mes rappels / mes notes  → consulter")
    print("  « ajoute payer le loyer à mes tâches pour vendredi »")
    print("  « rappelle-moi d'appeler maman dans 20 minutes »")
    print("  « note le code wifi : 1234 »")
    print()
    print("  SYSTÈME")
    print("  /aide                    → afficher cette aide")
    print("  /modele [nom]            → voir ou changer de modèle")
    print("  /voix on|off             → activer ou couper la voix")
    print("  /outils                  → outils que Jarvis utilise seul")
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

    # Rappels manqués pendant que Jarvis était fermé : affichés tout de
    # suite, puis vérification en arrière-plan
    for reminder in brain.tasks.pop_due_reminders():
        _notify(reminder, voice, reprint_prompt=False)
    scheduler = ReminderScheduler(brain.tasks, lambda r: _notify(r, voice)).start()

    try:
        _loop(brain, voice)
    finally:
        scheduler.stop()
        # Laisser Jarvis finir sa phrase avant de quitter
        voice.shutdown()


def _notify(reminder: Reminder, voice: "Voice", reprint_prompt: bool = True) -> None:
    """Affiche (et dit) un rappel arrivé à échéance."""
    late = ""
    if reminder.due_at < datetime.now() - timedelta(minutes=1):
        late = f" (prévu {format_when(reminder.due_at)})"
    print(f"\n  *** RAPPEL : {reminder.message}{late} ***\n", flush=True)
    if reprint_prompt:
        # Le rappel arrive pendant que l'utilisateur tape : réafficher l'invite
        print(f"{settings.USER_NAME} >>> ", end="", flush=True)
    voice.say(f"Rappel : {reminder.message}")


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
    elif name in ("outils", "tools"):
        tools = getattr(brain, "tools", None)
        if tools is None or not len(tools):
            print("  Aucun outil disponible.")
        else:
            state = "" if getattr(brain, "tools_enabled", True) else " (désactivés)"
            print(f"  Outils que Jarvis peut utiliser seul{state} :")
            for line in tools.describe().splitlines():
                print(f"  {line}")
    elif name in ("effacer", "clear", "nouveau"):
        brain.clear_conversation()
        print("  Conversation effacée.")
    else:
        print(f"  Commande inconnue : /{name} — tapez /aide")
    print()
    return True


def _confirm(action: str) -> bool:
    """Demande l'autorisation avant une action sensible."""
    print(f"\n  Jarvis veut exécuter : {action}")
    try:
        answer = input("  Autoriser ? (o/n) ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("o", "oui", "y", "yes")


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
        state = {"line_open": False, "streamed": False}

        def on_token(token: str) -> None:
            if not state["line_open"]:
                print("Jarvis >>> ", end="")
                state["line_open"] = True
            state["streamed"] = True
            print(token, end="", flush=True)

        def on_tool(name: str, args: dict) -> None:
            # Montrer quel outil Jarvis utilise, sur sa propre ligne
            if state["line_open"]:
                print()
                state["line_open"] = False
            shown = ", ".join(f"{k}={v!r}" for k, v in args.items())
            print(f"  [outil] {name}({shown})", flush=True)

        brain.on_tool = on_tool
        brain.confirm = _confirm
        try:
            response = brain.process(user_input, on_token=on_token)
        except KeyboardInterrupt:
            # Ctrl+C pendant une réponse : on l'interrompt sans quitter
            print("\n  (réponse interrompue)")
            print()
            continue

        if not state["streamed"]:
            # Commande directe : rien n'a été streamé, on affiche tout
            print(f"Jarvis >>> {response}", end="")
        print()

        # Dire la réponse à voix haute si disponible
        voice.say(response)
        print()
