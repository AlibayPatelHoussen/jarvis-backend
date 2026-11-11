"""
tools/builtin.py
================
Outils intégrés de Jarvis, exposés au modèle via le registre.

Ce sont les mêmes fonctionnalités que les commandes directes
(calcul, météo, actualités, mémoire), mais décrites pour que le
modèle puisse les utiliser seul, à partir d'une phrase naturelle :
« J'ai 3 réunions de 45 minutes, ça fait combien d'heures ? »
"""

from datetime import datetime

from core.prompt import format_date_fr
from tools.calculator import Calculator
from tools.news import News
from tools.registry import ToolRegistry
from tools.weather import Weather


def register_builtin_tools(registry: ToolRegistry, long_term=None) -> ToolRegistry:
    """
    Ajoute les outils intégrés au registre.

    Args:
        registry  : Registre à compléter
        long_term : Mémoire long terme (LongTermMemory) pour les outils
                    de mémoire. Si None, ces outils ne sont pas ajoutés.
    """

    @registry.tool()
    def calculer(expression: str) -> str:
        """
        Calcule une expression mathématique exacte. À utiliser pour tout
        calcul plutôt que de calculer de tête.

        Args:
            expression : Expression Python simple, ex. "(3 * 45) / 60" ou "2 ** 10".
                         Opérateurs : + - * / // % ** et parenthèses.
        """
        calc = Calculator()
        expression = expression.replace("×", "*").replace("÷", "/").replace("^", "**")
        return f"{expression} = {calc.format_result(calc.evaluate(expression))}"

    @registry.tool()
    def date_heure() -> str:
        """Donne la date et l'heure actuelles (jour de la semaine compris)."""
        now = datetime.now()
        return f"{format_date_fr(now)} (ISO : {now.isoformat(timespec='minutes')})"

    @registry.tool()
    def meteo(ville: str = "") -> str:
        """
        Donne la météo actuelle (température, ciel, vent, humidité).

        Args:
            ville : Nom de la ville. Vide = position actuelle de l'utilisateur.
        """
        return Weather().get(ville or None)

    @registry.tool()
    def actualites(categorie: str = "general") -> str:
        """
        Donne les titres de l'actualité du moment.

        Args:
            categorie : general, tech, sport, science ou international
        """
        news = News()
        categorie = news.detect_category(categorie) if categorie else "general"
        return news.format(news.get_headlines(category=categorie, max_articles=5), categorie)

    if long_term is None:
        return registry

    @registry.tool()
    def memoriser(fait: str) -> str:
        """
        Enregistre durablement une information sur l'utilisateur
        (prénom, ville, préférences, proches...). À utiliser quand
        l'utilisateur donne une information personnelle à retenir.

        Args:
            fait : Le fait à retenir, formulé à la 1re personne,
                   ex. "j'habite à Montréal"
        """
        long_term.add_fact(fait.strip())
        return f"Mémorisé : {fait.strip()}"

    @registry.tool()
    def souvenirs() -> str:
        """Liste tout ce que Jarvis sait durablement sur l'utilisateur."""
        facts = list(long_term.get_all().values())
        if not facts:
            return "Aucun fait mémorisé."
        return "\n".join(f"- {fact}" for fact in facts)

    @registry.tool()
    def oublier(mot_cle: str) -> str:
        """
        Oublie les faits mémorisés qui contiennent un mot-clé.

        Args:
            mot_cle : Mot à rechercher dans les faits à oublier
        """
        deleted = []
        for key, value in long_term.get_all().items():
            if mot_cle.lower() in value.lower():
                long_term.delete(key)
                deleted.append(value)
        return f"Oublié : {', '.join(deleted)}" if deleted else "Aucun fait trouvé."

    return registry
