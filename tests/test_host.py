"""
tests/test_host.py
==================
Outils fournis par une application hôte (tools/host.py), avec un faux Nexus.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from core.brain import Brain
from core.memory import LongTermMemory
from llm.ollama import Ollama
from tests.fake_ollama import FakeOllama
from tools.host import HostTools, sync_host_tools
from tools.registry import ToolRegistry

SECRET = "secret-partage"

MANIFEST = {
    "name": "Nexus",
    "description": "Serveur multimédia.",
    "tools": [
        {"name": "nexus_bibliotheque", "description": "Fait le point sur la bibliothèque.",
         "parameters": {"type": "object", "properties": {"type": {"type": "string"}},
                        "required": []},
         "confirm": False, "roles": ["admin", "user"]},
        {"name": "nexus_telecharger", "description": "Met un téléchargement en file.",
         "parameters": {"type": "object", "properties": {"id": {"type": "string"}},
                        "required": ["id"]},
         "confirm": False, "roles": ["admin"]},
        {"name": "nexus_supprimer_media", "description": "Supprime un titre.",
         "parameters": {"type": "object", "properties": {"id": {"type": "string"}},
                        "required": ["id"]},
         "confirm": True, "roles": ["admin"]},
        {"name": "nom invalide", "description": "ignoré"},
    ],
}


@pytest.fixture
def host_server():
    state = {"manifest": json.loads(json.dumps(MANIFEST)), "calls": [], "status": 200}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _ok(self):
            if self.headers.get("X-Jarvis-Secret") != SECRET:
                self._send(401, {"error": "Secret Jarvis invalide"})
                return False
            return True

        def do_GET(self):
            if self._ok():
                self._send(200, state["manifest"])

        def do_POST(self):
            if not self._ok():
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            name = self.path.rsplit("/", 1)[-1]
            state["calls"].append({"name": name, **body})
            if state["status"] != 200:
                self._send(state["status"], {"success": False, "error": "Titre not found"})
                return
            who, args = body["user"]["id"], body["arguments"]
            self._send(200, {"result": f"{name} fait pour {who} avec {args}"})

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{srv.server_address[1]}/api/jarvis/tools"
    yield state
    srv.shutdown()
    srv.server_close()


def test_manifest_and_roles(host_server):
    host = HostTools(host_server["url"], SECRET)
    assert host.refresh() is True
    assert host.name == "Nexus"
    assert host.tool_names() == ["nexus_bibliotheque", "nexus_telecharger", "nexus_supprimer_media"]

    admin = ToolRegistry()
    added = host.register_into(admin, "owner", "admin")
    assert added == host.tool_names()
    assert admin.get("nexus_supprimer_media").confirm is True
    assert admin.get("nexus_telecharger").parameters["required"] == ["id"]

    user = ToolRegistry()
    assert host.register_into(user, "42", "user") == ["nexus_bibliotheque"]


def test_calls_send_secret_user_and_arguments(host_server):
    host = HostTools(host_server["url"], SECRET)
    host.refresh()
    reg = ToolRegistry()
    host.register_into(reg, "owner", "admin")
    out = reg.execute("nexus_telecharger", {"id": "anisama:anime:one-piece"})
    assert out == "nexus_telecharger fait pour owner avec {'id': 'anisama:anime:one-piece'}"
    call = host_server["calls"][-1]
    assert call["user"] == {"id": "owner", "role": "admin"}
    assert reg.execute("nexus_supprimer_media", {"id": "x"}) == "Action refusée par l'utilisateur."
    assert len(host_server["calls"]) == 1


def test_errors_are_readable(host_server):
    host = HostTools(host_server["url"], SECRET)
    host.refresh()
    reg = ToolRegistry()
    host.register_into(reg, "owner", "admin")
    host_server["status"] = 404
    assert reg.execute("nexus_bibliotheque") == "Erreur de Nexus (404) : Titre not found"
    wrong = HostTools(host_server["url"], "mauvais")
    assert wrong.refresh() is False and wrong.tool_names() == []
    down = HostTools("http://127.0.0.1:9/api/jarvis/tools", SECRET)
    assert down.refresh() is False
    down._tools = MANIFEST["tools"][:1]
    reg2 = ToolRegistry()
    down.register_into(reg2, "owner", "admin")
    assert "ne répond pas" in reg2.execute("nexus_bibliotheque")


def test_refresh_is_throttled_and_sync_replaces_tools(host_server):
    host = HostTools(host_server["url"], SECRET, refresh_seconds=3600)
    reg = ToolRegistry()
    names = sync_host_tools(reg, host, "owner", "admin")
    assert "nexus_telecharger" in reg
    host_server["manifest"]["tools"] = host_server["manifest"]["tools"][:1]
    assert host.refresh() is False                   # pas avant l'échéance
    assert host.refresh(force=True) is True
    names = sync_host_tools(reg, host, "owner", "admin", previous=names)
    assert names == ["nexus_bibliotheque"] and "nexus_telecharger" not in reg
    assert sync_host_tools(reg, None, "owner", "admin", previous=names) == []
    assert "nexus_bibliotheque" not in reg


def test_not_configured():
    assert HostTools("", "x").configured is False
    assert HostTools("http://x", "").refresh() is False


def test_brain_uses_host_tools(host_server, tmp_path):
    host = HostTools(host_server["url"], SECRET)
    with FakeOllama() as fake:
        fake.replies += [
            {"content": "", "tool_calls": [{"function": {
                "name": "nexus_telecharger", "arguments": {"id": "movix:movie:438631"}}}]},
            {"content": "Dune est dans la file de téléchargement."},
        ]
        brain = Brain(llm=Ollama(host=fake.url, model="mistral"),
                      long_term=LongTermMemory(db_path=tmp_path / "m.db"),
                      host=host, user_id="owner")
        assert brain.process("Télécharge Dune") == "Dune est dans la file de téléchargement."
        sent = fake.requests[0]
        names = [t["function"]["name"] for t in sent["tools"]]
        assert "nexus_telecharger" in names and "calculer" in names
        assert "Application hôte « Nexus »" in sent["messages"][0]["content"]
        assert host_server["calls"][0]["user"] == {"id": "owner", "role": "admin"}
        tool_msg = [m for m in fake.requests[1]["messages"] if m["role"] == "tool"][0]
        assert tool_msg["content"].startswith("nexus_telecharger fait pour owner")


def test_user_role_brain_gets_only_allowed_host_tools(host_server, tmp_path):
    host = HostTools(host_server["url"], SECRET)
    with FakeOllama() as fake:
        brain = Brain(llm=Ollama(host=fake.url, model="mistral"),
                      long_term=LongTermMemory(db_path=tmp_path / "m.db"),
                      host=host, user_id="42", role="user")
        brain.process("Bonjour")
        names = [t["function"]["name"] for t in fake.requests[0]["tools"]]
        assert "nexus_bibliotheque" in names
        assert "nexus_telecharger" not in names and "nexus_supprimer_media" not in names
