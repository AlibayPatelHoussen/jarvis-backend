"""
tests/fake_ollama.py
====================
Faux serveur Ollama pour les tests.

Il imite l'API HTTP réelle (/api/tags, /api/chat, streaming en
JSON ligne par ligne, appels d'outils) : le vrai client HTTP de
Jarvis est donc testé sans avoir besoin d'Ollama ni d'un modèle.

Usage :
    with FakeOllama() as server:
        server.replies.append({"content": "Bonjour !"})
        client = Ollama(host=server.url)
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeOllama:
    def __init__(self, models=("mistral:latest",), supports_tools=True):
        self.models = list(models)
        self.supports_tools = supports_tools
        # Réponses à renvoyer, dans l'ordre. Chaque réponse est un dict
        # {"content": str, "tool_calls": [...]} ou {"error": str, "status": int}
        self.replies: list[dict] = []
        # Requêtes /api/chat reçues (payload JSON)
        self.requests: list[dict] = []
        self._server = None

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def __enter__(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, body, content_type="application/json"):
                data = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/api/tags":
                    models = [{"name": m} for m in fake.models]
                    self._send(200, json.dumps({"models": models}))
                else:
                    self._send(404, "{}")

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
                fake.requests.append(payload)

                model = payload.get("model", "")
                known = model in fake.models or f"{model}:latest" in fake.models
                if not known:
                    self._send(404, json.dumps({"error": f"model '{model}' not found"}))
                    return
                if payload.get("tools") and not fake.supports_tools:
                    self._send(400, json.dumps(
                        {"error": f"registry.ollama.ai/library/{model} does not support tools"}
                    ))
                    return

                reply = fake.replies.pop(0) if fake.replies else {"content": "ok"}
                if "error" in reply:
                    self._send(reply.get("status", 500), json.dumps({"error": reply["error"]}))
                    return

                message = {
                    "role": "assistant",
                    "content": reply.get("content", ""),
                }
                if reply.get("tool_calls"):
                    message["tool_calls"] = reply["tool_calls"]

                if not payload.get("stream"):
                    self._send(200, json.dumps({"message": message, "done": True}))
                    return

                # Streaming : un morceau par mot, puis le message final
                lines = []
                words = message["content"].split(" ")
                for i, word in enumerate(words):
                    piece = word if i == len(words) - 1 else word + " "
                    lines.append({"message": {"role": "assistant", "content": piece},
                                  "done": False})
                if message.get("tool_calls"):
                    lines.append({"message": {"role": "assistant", "content": "",
                                              "tool_calls": message["tool_calls"]},
                                  "done": False})
                lines.append({"message": {"role": "assistant", "content": ""},
                              "done": True})
                body = "\n".join(json.dumps(line) for line in lines) + "\n"
                self._send(200, body, "application/x-ndjson")

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        ).start()
        return self

    def __exit__(self, *args):
        self._server.shutdown()
        self._server.server_close()
        return False
