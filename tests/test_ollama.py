"""
tests/test_ollama.py
====================
Tests unitaires pour llm/ollama.py

On teste deux types de choses :
1. Tests sans Ollama (unitaires purs) - toujours rapides
2. Tests avec Ollama réel (intégration) - marqués @pytest.mark.integration
"""

import pytest
from llm.ollama import Ollama, OllamaError


# ─────────────────────────────────────────────
# Tests unitaires (pas besoin d'Ollama)
# ─────────────────────────────────────────────

def test_ollama_default_values():
    """Les valeurs par défaut viennent bien de settings."""
    from config import settings
    ollama = Ollama()
    assert ollama.host == settings.OLLAMA_HOST
    assert ollama.model == settings.OLLAMA_MODEL


def test_ollama_custom_values():
    """On peut surcharger host et model."""
    ollama = Ollama(host="http://test:11434", model="llama3.2")
    assert ollama.host == "http://test:11434"
    assert ollama.model == "llama3.2"


def test_ollama_unavailable():
    """Si Ollama n'est pas sur ce port, is_available() retourne False."""
    ollama = Ollama(host="http://localhost:9999")
    assert ollama.is_available() is False


def test_ask_raises_when_unavailable():
    """ask() doit lever OllamaError si Ollama n'est pas disponible."""
    ollama = Ollama(host="http://localhost:9999")
    with pytest.raises(OllamaError):
        ollama.ask("test")


# ─────────────────────────────────────────────
# Tests d'intégration (nécessitent Ollama)
# ─────────────────────────────────────────────

@pytest.mark.integration
def test_ollama_is_available_real():
    """Ollama doit être accessible sur le port par défaut."""
    ollama = Ollama()
    assert ollama.is_available() is True


@pytest.mark.integration
def test_get_models_returns_list():
    """get_models() doit retourner une liste non vide."""
    ollama = Ollama()
    models = ollama.get_models()
    assert isinstance(models, list)
    assert len(models) > 0


@pytest.mark.integration
def test_ask_returns_string():
    """ask() doit retourner une string non vide."""
    ollama = Ollama()
    response = ollama.ask("Réponds juste 'ok'.")
    assert isinstance(response, str)
    assert len(response) > 0


# ─────────────────────────────────────────────
# Tests avec le faux serveur Ollama
# ─────────────────────────────────────────────

from tests.fake_ollama import FakeOllama  # noqa: E402
from llm.ollama import OllamaModelMissing, OllamaToolsUnsupported  # noqa: E402


@pytest.fixture
def server():
    with FakeOllama(models=["mistral:latest", "qwen2.5:7b"]) as fake:
        yield fake


def test_has_model_accepts_implicit_latest(server):
    assert Ollama(host=server.url, model="mistral").has_model() is True
    assert Ollama(host=server.url, model="qwen2.5:7b").has_model() is True
    assert Ollama(host=server.url, model="llama3.1").has_model() is False


def test_chat_without_stream(server):
    server.replies.append({"content": "Bonjour !"})
    reply = Ollama(host=server.url, model="mistral").chat(
        [{"role": "user", "content": "Salut"}]
    )
    assert reply["content"] == "Bonjour !"
    assert reply["tool_calls"] == []
    assert server.requests[0]["stream"] is False


def test_chat_streams_tokens(server):
    server.replies.append({"content": "Il fait beau aujourd'hui"})
    tokens = []
    reply = Ollama(host=server.url, model="mistral").chat(
        [{"role": "user", "content": "Météo ?"}], on_token=tokens.append
    )
    assert len(tokens) == 4
    assert "".join(tokens) == "Il fait beau aujourd'hui"
    assert reply["content"] == "Il fait beau aujourd'hui"
    assert server.requests[0]["stream"] is True


@pytest.mark.parametrize("stream", [False, True])
def test_chat_returns_tool_calls(server, stream):
    server.replies.append({"content": "", "tool_calls": [
        {"function": {"name": "calculer", "arguments": {"expression": "2+2"}}},
        {"function": {"name": "meteo", "arguments": '{"ville": "Paris"}'}},
    ]})
    tools = [{"type": "function", "function": {"name": "calculer"}}]
    reply = Ollama(host=server.url, model="mistral").chat(
        [{"role": "user", "content": "2+2 ?"}],
        tools=tools,
        on_token=(lambda t: None) if stream else None,
    )
    assert reply["tool_calls"] == [
        {"function": {"name": "calculer", "arguments": {"expression": "2+2"}}},
        {"function": {"name": "meteo", "arguments": {"ville": "Paris"}}},
    ]
    assert server.requests[0]["tools"] == tools


def test_missing_model_error(server):
    with pytest.raises(OllamaModelMissing, match="ollama pull llama3.1"):
        Ollama(host=server.url, model="llama3.1").chat([{"role": "user", "content": "x"}])


def test_tools_unsupported_error():
    with FakeOllama(supports_tools=False) as fake:
        with pytest.raises(OllamaToolsUnsupported):
            Ollama(host=fake.url, model="mistral").chat(
                [{"role": "user", "content": "x"}], tools=[{"type": "function"}]
            )


def test_num_ctx_is_sent(server):
    Ollama(host=server.url, model="mistral", num_ctx=8192).ask("x")
    assert server.requests[0]["options"]["num_ctx"] == 8192
