"""
llm/ollama.py
=============
Connexion au modèle IA local via Ollama (gratuit, tourne sur ta machine).

Responsabilité unique : parler à l'API HTTP d'Ollama.

Deux façons de l'utiliser :
- ask()  : une question → une réponse texte (simple)
- chat() : liste de messages + outils optionnels, avec streaming
           optionnel. Retourne le message complet du modèle, y compris
           les appels d'outils ("tool_calls") qu'il a décidé de faire.

Pourquoi urllib et pas requests ?
- urllib est dans la stdlib Python (pas de dépendance externe)
"""

import json
import urllib.error
import urllib.request
from typing import Callable, Iterator, Optional

from config import settings


class OllamaError(Exception):
    """Erreur spécifique à Ollama."""
    pass


class OllamaToolsUnsupported(OllamaError):
    """Le modèle installé ne sait pas appeler d'outils."""
    pass


class OllamaModelMissing(OllamaError):
    """Le modèle demandé n'est pas installé dans Ollama."""
    pass


class Ollama:
    """
    Client pour communiquer avec Ollama.

    Usage :
        ollama = Ollama()
        print(ollama.ask("Bonjour !"))

        reply = ollama.chat(
            [{"role": "user", "content": "Bonjour"}],
            on_token=lambda t: print(t, end="", flush=True),
        )
    """

    def __init__(
        self,
        host: str = None,
        model: str = None,
        num_ctx: int = None,
    ):
        """
        Args:
            host    : URL d'Ollama (défaut : settings.OLLAMA_HOST)
            model   : Nom du modèle (défaut : settings.OLLAMA_MODEL)
            num_ctx : Taille du contexte (défaut : settings.OLLAMA_NUM_CTX)
        """
        self.host = (host or settings.OLLAMA_HOST).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.num_ctx = num_ctx or settings.OLLAMA_NUM_CTX

    # ─────────────────────────────────────────
    # État du serveur
    # ─────────────────────────────────────────

    def is_available(self) -> bool:
        """True si Ollama répond."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_models(self) -> list[str]:
        """Liste des modèles installés, ex: ["mistral:latest", "qwen2.5:7b"]."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def has_model(self, name: str = None) -> bool:
        """
        True si le modèle est installé.
        "mistral" correspond à "mistral:latest".
        """
        name = name or self.model
        wanted = name if ":" in name else f"{name}:latest"
        return any(m == name or m == wanted for m in self.get_models())

    # ─────────────────────────────────────────
    # Conversation
    # ─────────────────────────────────────────

    def ask(
        self,
        message: str,
        system_prompt: str = "",
        history: list[dict] = None,
        timeout: int = 120,
    ) -> str:
        """
        Envoie un message et retourne la réponse texte.

        Raises:
            OllamaError : Si Ollama n'est pas disponible ou renvoie une erreur
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": message})
        return self.chat(messages, timeout=timeout)["content"]

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        on_token: Optional[Callable[[str], None]] = None,
        timeout: int = 300,
    ) -> dict:
        """
        Envoie une conversation au modèle.

        Args:
            messages : [{"role": "system"|"user"|"assistant"|"tool", ...}]
            tools    : Schémas des outils (format Ollama / OpenAI)
            on_token : Si fourni, la réponse est streamée et chaque
                       morceau de texte est passé à cette fonction.
            timeout  : Secondes avant abandon

        Returns:
            {"role": "assistant", "content": str, "tool_calls": list}

        Raises:
            OllamaToolsUnsupported : le modèle ne gère pas les outils
            OllamaModelMissing     : le modèle n'est pas installé
            OllamaError            : toute autre erreur
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": on_token is not None,
            "options": {
                "temperature": 0.7,
                # Taille du contexte (prompt système + historique).
                # Trop petite, Ollama coupe le DÉBUT : le prompt
                # système et les faits connus sont perdus.
                "num_ctx": self.num_ctx,
            },
        }
        if tools:
            payload["tools"] = tools

        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if on_token is None:
                    data = json.loads(resp.read().decode("utf-8"))
                    return self._normalize(data.get("message") or {})
                return self._read_stream(resp, on_token)

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            self._raise_http_error(e.code, body)
        except urllib.error.URLError as e:
            raise OllamaError(
                f"Ollama n'est pas accessible sur {self.host} ({e.reason}). "
                "Lancez-le avec : ollama serve"
            )
        except OllamaError:
            raise
        except Exception as e:
            raise OllamaError(f"Erreur inattendue : {e}")

    # ─────────────────────────────────────────
    # Interne
    # ─────────────────────────────────────────

    def _read_stream(self, resp, on_token: Callable[[str], None]) -> dict:
        """Lit la réponse streamée (une ligne JSON par morceau)."""
        content = []
        tool_calls = []
        for chunk in self._iter_json_lines(resp):
            if chunk.get("error"):
                self._raise_http_error(500, json.dumps(chunk))
            message = chunk.get("message") or {}
            piece = message.get("content") or ""
            if piece:
                content.append(piece)
                on_token(piece)
            tool_calls.extend(message.get("tool_calls") or [])
            if chunk.get("done"):
                break
        return self._normalize({
            "content": "".join(content),
            "tool_calls": tool_calls,
        })

    @staticmethod
    def _iter_json_lines(resp) -> Iterator[dict]:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                yield json.loads(line)

    @staticmethod
    def _normalize(message: dict) -> dict:
        """Message assistant au format stable utilisé par Jarvis."""
        calls = []
        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):  # certains modèles renvoient du texte JSON
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            calls.append({"function": {"name": fn.get("name", ""), "arguments": args}})
        return {
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": calls,
        }

    def _raise_http_error(self, code: int, body: str) -> None:
        text = body.lower()
        if "does not support tools" in text:
            raise OllamaToolsUnsupported(
                f"Le modèle '{self.model}' ne sait pas utiliser d'outils."
            )
        if "not found" in text and "model" in text:
            raise OllamaModelMissing(
                f"Le modèle '{self.model}' n'est pas installé. "
                f"Installez-le avec : ollama pull {self.model}"
            )
        raise OllamaError(f"Ollama a retourné une erreur {code} : {body}")
