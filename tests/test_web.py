"""
tests/test_web.py
=================
Tests unitaires pour tools/web.py (serveur HTTP local, pas d'internet)
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tools import web
from tools.registry import ToolRegistry
from tools.web import html_to_text, parse_search_results, register_web_tools

PAGE = """<html><head><title>Jellyfin  - Accueil</title><style>body{}</style></head>
<body><nav>Menu</nav><h1>Bienvenue</h1><p>Serveur&nbsp;multimédia <b>libre</b>.</p>
<script>alert('x')</script><ul><li>Films</li><li>Séries</li></ul></body></html>"""

SEARCH = """
<div class="result results_links web-result">
  <h2><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fjellyfin.org%2F&amp;rut=x">
  <b>Jellyfin</b> : serveur multimédia</a></h2>
  <a class="result__snippet" href="#">Le serveur <b>libre</b> &amp; gratuit.</a>
</div>
<div class="result results_links web-result">
  <h2><a class="result__a" href="https://fr.wikipedia.org/wiki/Jellyfin">
  Jellyfin — Wikipédia</a></h2>
  <div class="result__snippet">Logiciel libre.</div>
</div>
"""


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body):
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send(PAGE)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            Handler.posted = self.rfile.read(length).decode()
            self._send(SEARCH)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01},
                     daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", Handler
    srv.shutdown()
    srv.server_close()


def test_html_to_text():
    title, text = html_to_text(PAGE)
    assert title == "Jellyfin - Accueil"
    assert text.splitlines() == ["Bienvenue", "Serveur multimédia libre.", "Films", "Séries"]


def test_parse_search_results():
    results = parse_search_results(SEARCH)
    assert results == [
        {"titre": "Jellyfin : serveur multimédia", "url": "https://jellyfin.org/",
         "extrait": "Le serveur libre & gratuit."},
        {"titre": "Jellyfin — Wikipédia", "url": "https://fr.wikipedia.org/wiki/Jellyfin",
         "extrait": "Logiciel libre."},
    ]
    assert parse_search_results("<html>rien</html>") == []


def test_lire_page_web(server):
    url, _ = server
    tools = register_web_tools(ToolRegistry())
    out = tools.execute("lire_page_web", {"url": url + "/accueil"})
    assert out.startswith("Titre : Jellyfin - Accueil")
    assert "Serveur multimédia libre." in out and "alert" not in out
    assert "http:// et https://" in tools.execute("lire_page_web", {"url": "file:///etc/passwd"})
    assert "impossible de charger" in tools.execute("lire_page_web",
                                                    {"url": "http://127.0.0.1:9/"})


def test_recherche_web(server, monkeypatch):
    url, handler = server
    monkeypatch.setattr(web, "SEARCH_URL", url + "/html/")
    out = register_web_tools(ToolRegistry()).execute("recherche_web", {"requete": "jellyfin"})
    assert handler.posted == "q=jellyfin"
    assert out.startswith("1. Jellyfin : serveur multimédia\n   https://jellyfin.org/")
