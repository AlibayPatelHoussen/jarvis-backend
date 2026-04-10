"""
core/brain.py
=============
Cerveau central de Jarvis.

Mise à jour : intégration de la mémoire.
- ShortTermMemory : historique de la conversation
- LongTermMemory  : faits persistants sur l'utilisateur

Le Brain injecte maintenant l'historique dans chaque
appel à Ollama pour que Jarvis se souvienne du contexte.
"""

from llm.ollama import Ollama, OllamaError
from core.memory import ShortTermMemory, LongTermMemory
from config import settings


SYSTEM_PROMPT = f"""Tu es Jarvis, un assistant IA personnel.

Caractéristiques :
- Langue : français (réponds toujours en français)
- Ton : professionnel, direct, efficace
- Tu t'appelles Jarvis
- L'utilisateur s'appelle {settings.USER_NAME}

Règles :
- Réponds de façon concise sauf si on te demande du détail
- Si tu ne sais pas, dis-le honnêtement
- Ne fabrique jamais d'informations
"""


class Brain:
    """
    Cerveau central de Jarvis.

    Usage :
        brain = Brain()
        response = brain.process("Bonjour !")
        print(response)
    """

    def __init__(self):
        self.llm = Ollama()
        self.short_term = ShortTermMemory(max_messages=20)
        self.long_term = LongTermMemory()

    def process(self, message: str) -> str:
        """
        Traite un message et retourne une réponse.

        Nouveauté : on passe l'historique à Ollama
        pour qu'il se souvienne du contexte.
        """
        message = message.strip()
        if not message:
            return ""

        try:
            # Récupérer l'historique court terme
            history = self.short_term.get_history()

            # Envoyer à Ollama avec l'historique
            response = self.llm.ask(
                message=message,
                system_prompt=SYSTEM_PROMPT,
                history=history
            )

            # Sauvegarder l'échange dans la mémoire court terme
            self.short_term.add("user", message)
            self.short_term.add("assistant", response)

            return response

        except OllamaError as e:
            return (
                f"Je ne peux pas répondre en ce moment : {e}\n"
                "Vérifiez qu'Ollama est lancé."
            )

    def remember(self, key: str, value: str) -> None:
        """
        Sauvegarde un fait en mémoire long terme.

        Args:
            key   : ex "prenom", "ville"
            value : ex "Houssen", "Montréal"
        """
        self.long_term.save(key, value)

    def recall(self, key: str) -> str:
        """
        Récupère un fait de la mémoire long terme.

        Returns:
            La valeur ou None si inconnue
        """
        return self.long_term.get(key)

    def clear_conversation(self) -> None:
        """Efface l'historique de la conversation en cours."""
        self.short_term.clear()

    def is_ready(self) -> bool:
        """Vérifie si Ollama est accessible."""
        return self.llm.is_available()
