"""
tools/web.py
============
Outils web gratuits, sans clé API :
- lire_page_web  : télécharge une page et en extrait le texte
- recherche_web  : recherche via DuckDuckGo (version HTML)

Fonctionne aussi pour les pages du réseau local (ex. l'interface d'un
service auto-hébergé sur http://192.168.1.10:8080).
"""

import html
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

MAX_PAGE_BYTES = 3_000_000
MAX_TEXT = 6000
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Jarvis/1.0",
    "Accept-Language": "fr,en;q=0.8",
}
SEARCH_URL = "https://html.duckduckgo.com/html/"


class WebError(Exception):
    pass


class _TextExtractor(HTMLParser):
    """Garde le texte visible d'une page HTML."""

    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title, self._skip, self._in_title = [], "", 0, False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def html_to_text(page: str) -> tuple[str, str]:
    """Retourne (titre, texte) d'une page HTML."""
    parser = _TextExtractor()
    parser.feed(page)
    return " ".join(parser.title.split()), parser.text()


def fetch(url: str, timeout: int = 15, data: bytes = None) -> str:
    if not re.match(r"https?://", url, re.IGNORECASE):
        raise WebError("seules les adresses http:// et https:// sont acceptées")
    req = urllib.request.Request(url, data=data, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(MAX_PAGE_BYTES)
            charset = resp.headers.get_content_charset() or "utf-8"
    except Exception as e:
        raise WebError(f"impossible de charger {url} : {e}")
    return raw.decode(charset, errors="replace")


def parse_search_results(page: str, limit: int = 6) -> list[dict]:
    """Extrait titre, lien et extrait des résultats DuckDuckGo HTML."""
    results = []
    blocks = re.split(r'<div[^>]+class="[^"]*\bresult\b', page)[1:]
    for block in blocks:
        link = re.search(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                         block, re.S)
        if not link:
            continue
        href = html.unescape(link.group(1))
        # DuckDuckGo passe par une redirection : //duckduckgo.com/l/?uddg=<vraie url>
        target = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg")
        url = target[0] if target else href
        snippet = re.search(r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div|td)>',
                            block, re.S)
        clean = lambda s: " ".join(html.unescape(re.sub(r"<[^>]+>", "", s)).split())  # noqa: E731
        results.append({
            "titre": clean(link.group(2)),
            "url": url,
            "extrait": clean(snippet.group(1)) if snippet else "",
        })
        if len(results) >= limit:
            break
    return results


def register_web_tools(registry):
    """Ajoute les outils web au registre."""

    @registry.tool()
    def lire_page_web(url: str) -> str:
        """
        Télécharge une page web et renvoie son texte (pour la lire ou la
        résumer). Marche aussi avec les adresses du réseau local.

        Args:
            url : Adresse complète, ex. "https://fr.wikipedia.org/wiki/Python"
        """
        try:
            page = fetch(url)
        except WebError as e:
            return f"Erreur : {e}"
        title, text = html_to_text(page)
        if len(text) > MAX_TEXT:
            text = text[:MAX_TEXT] + "\n... (page tronquée)"
        return f"Titre : {title or '(sans titre)'}\nURL : {url}\n\n{text or '(aucun texte)'}"

    @registry.tool()
    def recherche_web(requete: str) -> str:
        """
        Cherche sur le web (DuckDuckGo) et renvoie les premiers résultats
        (titre, lien, extrait). Utilise lire_page_web pour lire un résultat.

        Args:
            requete : Ce qu'il faut chercher
        """
        try:
            page = fetch(SEARCH_URL, data=urllib.parse.urlencode({"q": requete}).encode())
        except WebError as e:
            return f"Erreur : {e}"
        results = parse_search_results(page)
        if not results:
            return "Aucun résultat."
        return "\n\n".join(
            f"{i}. {r['titre']}\n   {r['url']}\n   {r['extrait']}"
            for i, r in enumerate(results, 1)
        )

    return registry
