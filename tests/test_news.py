from tools.news import News, Article, RSS_FEEDS
"""
tests/test_news.py
==================
Tests unitaires pour tools/news.py
"""

import pytest


@pytest.fixture
def news():
    return News()


# ─────────────────────────────────────────────
# Tests unitaires
# ─────────────────────────────────────────────

def test_rss_feeds_not_empty():
    """Les flux RSS doivent être définis."""
    assert len(RSS_FEEDS) > 0


def test_rss_feeds_has_general():
    """La catégorie general doit exister."""
    assert "general" in RSS_FEEDS


def test_rss_feeds_has_tech():
    """La catégorie tech doit exister."""
    assert "tech" in RSS_FEEDS


def test_article_str():
    """__str__ doit inclure source et titre."""
    article = Article(title="Titre test", source="Source test")
    result = str(article)
    assert "Titre test" in result
    assert "Source test" in result


def test_clean_text_removes_html(news):
    """_clean_text() doit supprimer les balises HTML."""
    result = news._clean_text("<p>Bonjour <b>monde</b></p>")
    assert "<" not in result
    assert "Bonjour monde" in result


def test_clean_text_decodes_entities(news):
    """_clean_text() doit décoder les entités HTML."""
    result = news._clean_text("AT&amp;T")
    assert result == "AT&T"


def test_clean_text_removes_extra_spaces(news):
    """_clean_text() doit supprimer les espaces multiples."""
    result = news._clean_text("Bonjour   monde")
    assert "  " not in result


def test_detect_category_tech(news):
    """Doit détecter la catégorie tech."""
    assert news.detect_category("actualités tech") == "tech"


def test_detect_category_sport(news):
    """Doit détecter la catégorie sport."""
    assert news.detect_category("résultats foot") == "sport"


def test_detect_category_default(news):
    """Doit retourner general par défaut."""
    assert news.detect_category("les nouvelles du jour") == "general"


def test_format_output(news):
    """format() doit retourner une string avec les titres."""
    articles = [
        Article(title="Titre 1", source="Source 1"),
        Article(title="Titre 2", source="Source 2"),
    ]
    result = news.format(articles, "general")
    assert "Titre 1" in result
    assert "Titre 2" in result
    assert "Actualités" in result


# ─────────────────────────────────────────────
# Tests d'intégration
# ─────────────────────────────────────────────

@pytest.mark.integration
def test_get_headlines_general(news):
    """get_headlines() doit retourner des articles."""
    articles = news.get_headlines("general", max_articles=3)
    assert len(articles) > 0
    assert isinstance(articles[0], Article)


@pytest.mark.integration
def test_get_headlines_max_articles(news):
    """get_headlines() ne doit pas dépasser max_articles."""
    articles = news.get_headlines("general", max_articles=3)
    assert len(articles) <= 3


# ─────────────────────────────────────────────
# Non-régression
# ─────────────────────────────────────────────

def test_clean_text_decodes_all_entities(news):
    assert news._clean_text("L&#8217;été &eacute;tait chaud") == "L’été était chaud"


def test_clean_text_removes_encoded_html(news):
    text = "&lt;p&gt;Bonjour &lt;b&gt;monde&lt;/b&gt;&lt;/p&gt;"
    assert news._clean_text(text) == "Bonjour monde"


@pytest.mark.parametrize("text", ["sociales", "médias", "spécial", "initiatives"])
def test_detect_category_matches_whole_words_only(news, text):
    assert news.detect_category(text) == "general"


@pytest.mark.parametrize("text, expected", [
    ("IA", "tech"),
    ("actualités de l'IA", "tech"),
    ("Sports", "sport"),
    ("du monde", "international"),
    ("santé", "science"),
])
def test_detect_category_keywords(news, text, expected):
    assert news.detect_category(text) == expected


def test_format_adds_ellipsis_only_when_truncated(news):
    short = news.format([Article("Titre court", "S", "Résumé court")])
    assert "Résumé court..." not in short
    assert "Résumé court" in short
    long = news.format([Article("Titre long", "S", "x" * 150)])
    assert "x" * 100 + "..." in long


def test_parse_feed_respects_declared_encoding(news, monkeypatch):
    xml = (
        '<?xml version="1.0" encoding="ISO-8859-1"?>'
        "<rss><channel><item><title>Été à Montréal</title></item></channel></rss>"
    ).encode("iso-8859-1")

    class FakeResponse:
        def read(self):
            return xml

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse())
    articles = news._parse_feed("http://exemple.invalid/rss", "Test")
    assert articles[0].title == "Été à Montréal"
