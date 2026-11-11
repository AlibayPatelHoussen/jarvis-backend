"""
core/prompt.py
==============
Construction du prompt système de Jarvis.

Le prompt est reconstruit à CHAQUE message : il contient la date et
l'heure actuelles (indispensable pour « demain », « dans 2 heures »...)
et ce que Jarvis sait de l'utilisateur.
"""

from datetime import datetime
from typing import Optional

from config import settings

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
    "août", "septembre", "octobre", "novembre", "décembre",
]

LANGUAGES = {
    "fr": "français (réponds toujours en français)",
    "en": "anglais (always answer in English)",
}


def format_date_fr(now: datetime) -> str:
    """Ex : « mercredi 11 novembre 2026, 14 h 05 »."""
    return (
        f"{JOURS[now.weekday()]} {now.day} {MOIS[now.month - 1]} {now.year}, "
        f"{now.hour} h {now.minute:02d}"
    )


def build_system_prompt(
    known_facts: Optional[list[str]] = None,
    now: Optional[datetime] = None,
    extra_sections: Optional[list[str]] = None,
) -> str:
    """
    Args:
        known_facts    : Faits connus sur l'utilisateur
        now            : Date/heure courante (paramètre pour les tests)
        extra_sections : Blocs de texte ajoutés à la fin (environnement,
                         consignes des outils...)
    """
    now = now or datetime.now()
    language = LANGUAGES.get(settings.LANGUAGE, LANGUAGES["fr"])

    prompt = f"""Tu es Jarvis, un assistant IA personnel.

Caractéristiques :
- Langue : {language}
- Ton : professionnel, direct, efficace
- Tu t'appelles Jarvis
- L'utilisateur s'appelle {settings.USER_NAME}

Contexte :
- Nous sommes le {format_date_fr(now)} (date ISO : {now.strftime("%Y-%m-%dT%H:%M")})

Règles :
- Réponds de façon concise sauf si on te demande du détail
- Si tu ne sais pas, dis-le honnêtement
- Ne fabrique jamais d'informations
"""
    if known_facts:
        prompt += "\nCe que tu sais sur l'utilisateur :\n"
        prompt += "\n".join(f"- {fact}" for fact in known_facts) + "\n"
    for section in extra_sections or []:
        prompt += f"\n{section.strip()}\n"
    return prompt
