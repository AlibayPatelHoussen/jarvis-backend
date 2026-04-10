"""
core/brain.py
=============
Cerveau central de Jarvis.

Responsabilité unique : recevoir un message, décider quoi
faire, et retourner une réponse.

Le Brain ne sait pas :
- Comment afficher la réponse (rôle de l'interface)
- Comment parler à Ollama (rôle de llm/ollama.py)
- Comment sauvegarder (rôle de memory.py — à venir)

Le Brain sait :
- Quel module appeler selon le message
- Comment construire le prompt système
- Comment gérer les erreurs proprement
"""

from llm.ollama import Ollama, OllamaError
from config import settings


# Prompt système — définit la personnalité de Jarvis
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
        """
        Initialise le Brain.

        On crée le client Ollama ici.
        Plus tard on ajoutera la mémoire et les outils.
        """
        self.llm = Ollama()

    def process(self, message: str) -> str:
        """
        Traite un message et retourne une réponse.

        C'est la méthode principale du Brain.
        Toute l'interface passe par ici.

        Args:
            message : Le message de l'utilisateur

        Returns:
            La réponse de Jarvis en string
        """
        # Valider l'entrée
        message = message.strip()
        if not message:
            return ""

        # Envoyer à Ollama et retourner la réponse
        try:
            response = self.llm.ask(
                message=message,
                system_prompt=SYSTEM_PROMPT
            )
            return response

        except OllamaError as e:
            # Ollama n'est pas disponible — message clair pour l'utilisateur
            return (
                f"Je ne peux pas répondre en ce moment : {e}\n"
                "Vérifiez qu'Ollama est lancé."
            )

    def is_ready(self) -> bool:
        """
        Vérifie si le Brain est opérationnel.

        Returns:
            True si Ollama est accessible, False sinon
        """
        return self.llm.is_available()