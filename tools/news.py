"""
tools/news.py
=============
Actualités en temps réel pour Jarvis.

Utilise les flux RSS — gratuit, sans clé API.
Le RSS est un standard XML que tous les grands
médias publient gratuitement.

Sources disponibles par catégorie :
- general     : Le Monde, France Info, BFM TV
- tech        : 01net, ZDNet
- sport       : L'Équipe
- science     : Futura Sciences
- international : RFI, France 24
"""

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass


RSS_FEEDS = {
    "general": [
        ("Le Monde", "https://www.lemonde.fr/rss/une.xml"),
        ("France Info", "https://www.francetvinfo.fr/titres.rss"),
    ],
    "tech": [
        ("01net", "https://www.01net.com/rss/"),
        ("ZDNet", "https://www.zdnet.fr/feeds/rss/actualites/"),
    ],
    "sport": [
        ("RMC Sport", "https://www.rmcsport.bfmtv.com/rss/football/"),
        ("Eurosport", "https://www.eurosport.fr/rss.xml"),
    ],
    "science": [
        ("Futura Sciences", "https://www.futura-sciences.com/rss/actualites.xml"),
    ],
    "international": [
        ("RFI", "https://www.rfi.fr/fr/rss"),
        ("France 24", "https://www.france24.com/fr/rss"),
    ],
}

# Mots-clés (mots entiers) pour détecter la catégorie demandée
CATEGORY_KEYWORDS = {
    "tech": ["tech", "technos?", "technologies?", "informatique", "ia", "numérique"],
    "sport": ["sports?", "foot", "football", "tennis", "rugby"],
    "science": ["sciences?", "santé", "médecine", "recherche"],
    "international": ["monde", "international(?:e|es)?", "étranger"],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis/1.0",
    "Accept": "application/rss+xml, application/xml, text/xml",
}


class NewsError(Exception):
    """Erreur spécifique aux actualités."""
    pass


@dataclass
class Article:
    """Un article d'actualité."""
    title: str
    source: str
    description: str = ""

    def __str__(self) -> str:
        return f"[{self.source}] {self.title}"


class News:
    """
    Récupère les actualités via RSS.

    Usage :
        news = News()
        articles = news.get_headlines()
        for article in articles:
            print(article)
    """

    def get_headlines(
        self,
        category: str = "general",
        max_articles: int = 5
    ) -> list[Article]:
        """
        Récupère les titres d'actualité.

        Args:
            category    : Catégorie (general, tech, sport,
                          science, international)
            max_articles: Nombre maximum d'articles

        Returns:
            Liste d'Article

        Raises:
            NewsError : Si impossible de récupérer les actualités
        """
        feeds = RSS_FEEDS.get(category, RSS_FEEDS["general"])
        articles = []

        for source_name, url in feeds:
            try:
                feed_articles = self._parse_feed(url, source_name)
                articles.extend(feed_articles)
                if len(articles) >= max_articles * 2:
                    break
            except Exception:
                continue

        if not articles:
            raise NewsError(
                f"Impossible de récupérer les actualités '{category}'."
            )

        return articles[:max_articles]

    def _parse_feed(self, url: str, source: str) -> list[Article]:
        """
        Parse un flux RSS et retourne les articles.

        Args:
            url    : URL du flux RSS
            source : Nom de la source

        Returns:
            Liste d'Article
        """
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            # On passe les octets bruts : ElementTree lit l'encodage
            # déclaré dans le flux (ex. ISO-8859-1) au lieu de forcer UTF-8
            content = resp.read()

        root = ET.fromstring(content)
        articles = []

        # Parcourir les items RSS
        for item in root.iter("item"):
            title_el = item.find("title")
            desc_el = item.find("description")

            if title_el is None or not title_el.text:
                continue

            title = self._clean_text(title_el.text)
            description = ""
            if desc_el is not None and desc_el.text:
                description = self._clean_text(desc_el.text)[:150]

            if title and len(title) > 5:
                articles.append(Article(
                    title=title,
                    source=source,
                    description=description
                ))

        return articles

    def _clean_text(self, text: str) -> str:
        """Nettoie le texte HTML d'un article RSS."""
        # Décoder toutes les entités HTML (&eacute;, &#8217;, &lt;...)
        # AVANT de retirer les balises : les descriptions RSS contiennent
        # souvent du HTML encodé (&lt;p&gt;...&lt;/p&gt;)
        text = html.unescape(text)
        # Supprimer les balises HTML
        text = re.sub(r"<[^>]+>", "", text)
        # Supprimer les espaces multiples
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def format(
        self,
        articles: list[Article],
        category: str = "general"
    ) -> str:
        """
        Formate les articles pour l'affichage.

        Args:
            articles : Liste d'articles
            category : Catégorie pour le titre

        Returns:
            String formatée
        """
        category_names = {
            "general": "Actualités",
            "tech": "Tech",
            "sport": "Sport",
            "science": "Science",
            "international": "International",
        }
        title = category_names.get(category, "Actualités")

        lines = [f"=== {title} ===", ""]
        for i, article in enumerate(articles, 1):
            lines.append(f"{i}. {article.title}")
            lines.append(f"   [{article.source}]")
            if article.description:
                desc = article.description
                if len(desc) > 100:
                    desc = desc[:100].rstrip() + "..."
                lines.append(f"   {desc}")
            lines.append("")

        return "\n".join(lines)

    def detect_category(self, text: str) -> str:
        """
        Détecte la catégorie depuis le texte.

        Args:
            text : Message de l'utilisateur

        Returns:
            Catégorie détectée
        """
        # Recherche par mot entier : avec une simple recherche de
        # sous-chaîne, "ia" était trouvé dans "sociales" ou "médias"
        for category, keywords in CATEGORY_KEYWORDS.items():
            pattern = r"\b(?:" + "|".join(keywords) + r")\b"
            if re.search(pattern, text, re.IGNORECASE):
                return category
        return "general"
