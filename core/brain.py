"""
core/brain.py
=============
Cerveau central de Jarvis.
Gère la mémoire court terme et long terme.
"""

import re
from tools.calculator import Calculator, CalculatorError
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

# Commandes de mémoire reconnues par le Brain
REMEMBER_PATTERNS = [
    r"souviens-toi que (.+)",
    r"retiens que (.+)",
    r"note que (.+)",
    r"mémorise que (.+)",
]

RECALL_PATTERNS = [
    r"que sais-tu de moi",
    r"qu'est-ce que tu sais de moi",
    r"ce que tu sais de moi",
    r"tes informations sur moi",
]

FORGET_PATTERNS = [
    r"oublie (.+)",
    r"efface (.+)",
    r"supprime (.+)",
]

CLEAR_PATTERNS = [
    r"nouvelle conversation",
    r"efface la conversation",
    r"recommence",
    r"oublie tout",
]
CALC_PATTERNS = [
    r"calcule?\s+(.+)",
    r"combien\s+(?:fait|vaut)\s+(.+)",
    r"(?:résultat|résoudre)\s+(.+)",
]


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

        Vérifie d'abord si c'est une commande de mémoire.
        Sinon envoie au LLM avec le contexte.
        """
        message = message.strip()
        if not message:
            return ""

        # Vérifier les commandes de mémoire
        memory_response = self._handle_memory_commands(message)
        if memory_response is not None:
            return memory_response

        # Construire le contexte long terme
        long_term_context = self._build_long_term_context()

        # Construire le prompt système enrichi
        system = SYSTEM_PROMPT
        if long_term_context:
            system += f"\n\nCe que tu sais sur l'utilisateur :\n{long_term_context}"

        try:
            history = self.short_term.get_history()
            response = self.llm.ask(
                message=message,
                system_prompt=system,
                history=history
            )
            self.short_term.add("user", message)
            self.short_term.add("assistant", response)
            return response

        except OllamaError as e:
            return (
                f"Je ne peux pas répondre en ce moment : {e}\n"
                "Vérifiez qu'Ollama est lancé."
            )

    def _handle_memory_commands(self, message: str) -> str | None:
        """
        Détecte et traite les commandes de mémoire.

        Returns:
            Une réponse string si c'est une commande mémoire.
            None si ce n'est pas une commande mémoire.
        """
        msg_lower = message.lower()

        # "souviens-toi que..."
        for pattern in REMEMBER_PATTERNS:
            match = re.search(pattern, msg_lower)
            if match:
                fact = match.group(1).strip()
                key = f"fact_{self.long_term.count() + 1}"
                self.long_term.save(key, fact)
                return f"Noté ! Je me souviendrai que {fact}."

        # "que sais-tu de moi ?"
        for pattern in RECALL_PATTERNS:
            if re.search(pattern, msg_lower):
                return self._format_known_facts()

        # "oublie..."
        for pattern in FORGET_PATTERNS:
            match = re.search(pattern, msg_lower)
            if match:
                target = match.group(1).strip()
                return self._forget_fact(target)

        # "nouvelle conversation"
        for pattern in CLEAR_PATTERNS:
            if re.search(pattern, msg_lower):
                self.short_term.clear()
                return "Conversation effacée. Repartons de zéro !"

        # Calcul mathématique
        for pattern in CALC_PATTERNS:
            match = re.search(pattern, msg_lower)
            if match:
                expression = match.group(1).strip()
                return self._calculate(expression)

        return None

    def _build_long_term_context(self) -> str:
        """
        Construit un résumé des faits connus pour
        l'injecter dans le prompt système.
        """
        facts = self.long_term.get_all()
        if not facts:
            return ""
        lines = [f"- {value}" for value in facts.values()]
        return "\n".join(lines)

    def _format_known_facts(self) -> str:
        """Formate les faits connus pour l'affichage."""
        facts = self.long_term.get_all()
        if not facts:
            return "Je ne sais rien de particulier sur toi encore."
        lines = ["Voici ce que je sais sur toi :"]
        for value in facts.values():
            lines.append(f"  - {value}")
        return "\n".join(lines)

    def _forget_fact(self, target: str) -> str:
        """Supprime un fait qui contient le mot cible."""
        facts = self.long_term.get_all()
        deleted = []
        for key, value in facts.items():
            if target.lower() in value.lower():
                self.long_term.delete(key)
                deleted.append(value)
        if deleted:
            return f"J'ai oublié : {', '.join(deleted)}."
        return f"Je n'ai rien trouvé concernant '{target}'."

    def remember(self, key: str, value: str) -> None:
        """Sauvegarde un fait en mémoire long terme."""
        self.long_term.save(key, value)

    def recall(self, key: str) -> str:
        """Récupère un fait de la mémoire long terme."""
        return self.long_term.get(key)

    def clear_conversation(self) -> None:
        """Efface l'historique de la conversation en cours."""
        self.short_term.clear()

    def is_ready(self) -> bool:
        """Vérifie si Ollama est accessible."""
        return self.llm.is_available()

    def _calculate(self, expression: str) -> str:
        """Évalue une expression mathématique."""
        calc = Calculator()
        try:
            result = calc.evaluate(expression)
            return f"{expression} = {calc.format_result(result)}"
        except CalculatorError as e:
            return f"Je ne peux pas calculer ça : {e}"
