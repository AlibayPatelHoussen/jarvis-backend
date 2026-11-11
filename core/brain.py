"""
core/brain.py
=============
Cerveau central de Jarvis.
Gère la mémoire court terme et long terme.
"""

import re
from typing import Callable, Optional
from tools.calculator import Calculator, CalculatorError
from llm.ollama import Ollama, OllamaError
from core.prompt import build_system_prompt
from core.memory import ShortTermMemory, LongTermMemory
from tools.weather import Weather, WeatherError
from tools.news import News, NewsError


# Commandes de mémoire reconnues par le Brain.
# Les motifs sont ancrés en début de message (^) pour ne pas
# déclencher une commande au milieu d'une phrase normale.
# Ils sont appliqués sans tenir compte de la casse (re.IGNORECASE)
# sur le message original, pour conserver la casse des faits.
_END = r"\s*[.!?]*\s*$"  # ponctuation finale optionnelle

REMEMBER_PATTERNS = [
    r"^souviens-toi que (.+)",
    r"^retiens que (.+)",
    r"^note que (.+)",
    r"^mémorise que (.+)",
]

RECALL_PATTERNS = [
    r"^que sais-tu de moi" + _END,
    r"^qu'est-ce que tu sais de moi" + _END,
    r"^(?:dis-moi )?ce que tu sais de moi" + _END,
    r"^(?:quelles sont )?tes informations sur moi" + _END,
]

FORGET_PATTERNS = [
    r"^oublie (.+)",
    r"^efface (.+)",
    r"^supprime (.+)",
]

# Vérifiés AVANT FORGET_PATTERNS : "oublie tout" et
# "efface la conversation" correspondent aussi à "oublie/efface (.+)".
CLEAR_PATTERNS = [
    r"^nouvelle conversation" + _END,
    r"^efface la conversation" + _END,
    r"^recommence" + _END,
    r"^oublie tout" + _END,
]

# Outils : mêmes règles que les commandes mémoire (début de message,
# ponctuation finale ignorée, casse conservée pour les villes).
CALC_PATTERNS = [
    r"^calcul(?:e|er)?\s+(.+)",
    r"^combien (?:fait|font|vaut|valent)\s+(.+)",
    r"^(?:résultat de|résous|résoudre)\s+(.+)",
]
_PLACE = r"(?:\s+(?:à|a|en|au|aux|de|du|pour)\s+(.+?))?"
WEATHER_PATTERNS = [
    r"^(?:la |quelle est la )?m[eé]t[eé]o" + _PLACE + _END,
    r"^(?:quel temps fait-il|quel temps il fait|il fait quel temps)"
    + _PLACE + _END,
    r"^(?:la |quelle est la )?temp[eé]rature" + _PLACE + _END,
]
NEWS_PATTERNS = [
    r"^(?:les |des )?actualit[eé]s?(?:\s+(.+?))?" + _END,
    r"^(?:les |des )?news(?:\s+(.+?))?" + _END,
    r"^(?:quoi de neuf|les nouvelles)(?:\s+(.+?))?" + _END,
    r"^(?:les )?titres(?: du jour)?()" + _END,
    r"^(?:le )?journal(?: du jour)?()" + _END,
]


def _clean(text: str) -> str:
    """Retire les espaces et la ponctuation finale d'un fragment."""
    return text.strip().rstrip(".!?").strip()


class Brain:
    """
    Cerveau central de Jarvis.

    Usage :
        brain = Brain()
        response = brain.process("Bonjour !")
        print(response)
    """

    def __init__(
        self,
        llm: Ollama = None,
        long_term: LongTermMemory = None,
    ):
        """
        Args:
            llm       : Client LLM (défaut : Ollama())
            long_term : Mémoire long terme (défaut : data/memory.db).
                        Les tests passent une base temporaire pour ne
                        pas toucher à la vraie mémoire.
        """
        self.llm = llm or Ollama()
        self.short_term = ShortTermMemory(max_messages=20)
        self.long_term = long_term or LongTermMemory()

    def process(
        self,
        message: str,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Traite un message et retourne une réponse.

        Vérifie d'abord si c'est une commande directe (mémoire, calcul,
        météo, actualités). Sinon envoie au LLM avec le contexte.

        Args:
            message  : Message de l'utilisateur
            on_token : Si fourni, la réponse du LLM est streamée morceau
                       par morceau vers cette fonction (affichage en direct).
                       Les réponses des commandes directes ne passent pas
                       par on_token : elles sont seulement retournées.
        """
        message = message.strip()
        if not message:
            return ""

        # Vérifier les commandes directes
        direct = self._handle_memory_commands(message)
        if direct is not None:
            return direct

        system = build_system_prompt(
            known_facts=list(self.long_term.get_all().values())
        )
        messages = [{"role": "system", "content": system}]
        messages += self.short_term.get_history()
        messages.append({"role": "user", "content": message})

        try:
            reply = self.llm.chat(messages, on_token=on_token)
        except OllamaError as e:
            return f"Je ne peux pas répondre en ce moment : {e}"

        response = reply["content"]
        self.short_term.add("user", message)
        self.short_term.add("assistant", response)
        return response

    def _handle_memory_commands(self, message: str) -> str | None:
        """
        Détecte et traite les commandes de mémoire.

        Returns:
            Une réponse string si c'est une commande mémoire.
            None si ce n'est pas une commande mémoire.
        """

        flags = re.IGNORECASE

        # "nouvelle conversation" — en premier, car "oublie tout"
        # correspondrait sinon à la commande "oublie ..."
        for pattern in CLEAR_PATTERNS:
            if re.search(pattern, message, flags):
                self.short_term.clear()
                return "Conversation effacée. Repartons de zéro !"

        # "souviens-toi que..."
        for pattern in REMEMBER_PATTERNS:
            match = re.search(pattern, message, flags)
            if match:
                fact = _clean(match.group(1))
                if not fact:
                    continue
                self.long_term.save(self._next_fact_key(), fact)
                return f"Noté ! Je me souviendrai que {fact}."

        # "que sais-tu de moi ?"
        for pattern in RECALL_PATTERNS:
            if re.search(pattern, message, flags):
                return self._format_known_facts()

        # "oublie..."
        for pattern in FORGET_PATTERNS:
            match = re.search(pattern, message, flags)
            if match:
                target = _clean(match.group(1))
                if not target:
                    continue
                return self._forget_fact(target)

        # Calcul mathématique — seulement s'il y a au moins un chiffre,
        # sinon "résous ce problème" partirait à la calculatrice
        for pattern in CALC_PATTERNS:
            match = re.search(pattern, message, flags)
            if match:
                expression = _clean(match.group(1))
                if not re.search(r"\d", expression):
                    continue
                return self._calculate(expression)

        # Météo
        for pattern in WEATHER_PATTERNS:
            match = re.search(pattern, message, flags)
            if match:
                city = _clean(match.group(1)) if match.group(1) else None
                return self._get_weather(city or None)

        # Actualités
        for pattern in NEWS_PATTERNS:
            match = re.search(pattern, message, flags)
            if match:
                category_hint = _clean(match.group(1) or "")
                return self._get_news(category_hint)

        return None

    def _next_fact_key(self) -> str:
        """
        Génère une clé libre pour un nouveau fait.

        On prend le plus grand numéro existant + 1 (et non le nombre
        de faits + 1) : après une suppression, le compte baisse et
        on écraserait un fait existant.
        """
        numbers = [
            int(key[5:]) for key in self.long_term.get_all()
            if key.startswith("fact_") and key[5:].isdigit()
        ]
        return f"fact_{max(numbers, default=0) + 1}"

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

    def health(self) -> Optional[str]:
        """
        Vérifie que Jarvis peut discuter.

        Returns:
            None si tout va bien, sinon un message expliquant quoi faire.
        """
        if not self.llm.is_available():
            return (
                f"Ollama n'est pas accessible sur {self.llm.host}. "
                "Lancez-le avec : ollama serve"
            )
        if not self.llm.has_model():
            return (
                f"Le modèle '{self.llm.model}' n'est pas installé. "
                f"Installez-le avec : ollama pull {self.llm.model}"
            )
        return None

    def _calculate(self, expression: str) -> str:
        """Évalue une expression mathématique."""
        calc = Calculator()
        try:
            result = calc.evaluate(expression)
            return f"{expression} = {calc.format_result(result)}"
        except CalculatorError as e:
            return f"Je ne peux pas calculer ça : {e}"

    def _get_weather(self, city: str = None) -> str:
        """Récupère la météo actuelle."""
        weather = Weather()
        try:
            return weather.get(city)
        except WeatherError as e:
            return f"Impossible d'obtenir la météo : {e}"

    def _get_news(self, category_hint: str = "") -> str:
        """Récupère les actualités."""
        news = News()
        try:
            category = news.detect_category(
                category_hint) if category_hint else "general"
            articles = news.get_headlines(category=category, max_articles=5)
            return news.format(articles, category)
        except NewsError as e:
            return f"Impossible d'obtenir les actualités : {e}"
