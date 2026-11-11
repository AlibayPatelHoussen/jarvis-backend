"""
tests/test_api.py
=================
Tests de l'API serveur (api/server.py) avec un faux Ollama.
"""

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.server import create_app
from core.environment import Environment
from core.sessions import NotificationCenter, SessionManager
from llm.ollama import Ollama
from tests.fake_ollama import FakeOllama
from tools.tasks import TaskStore

KEY = "cle-de-test-tres-secrete"
AUTH = {"Authorization": f"Bearer {KEY}"}


@pytest.fixture
def ollama():
    with FakeOllama(models=["qwen2.5:7b"]) as fake:
        yield fake


@pytest.fixture
def setup(ollama, tmp_path):
    env = Environment(os_name="Linux", os_version="6", hostname="nexus", user="srv",
                      shell="/bin/bash", cwd=tmp_path, workspace=tmp_path,
                      programs={"conteneurs": ["docker"]})
    sessions = SessionManager(tmp_path / "data", env,
                              lambda: Ollama(host=ollama.url, model="qwen2.5:7b"))
    notifications = NotificationCenter(sessions)
    app = create_app(sessions, KEY, notifications, confirm_timeout=5, owner_name="Houssen")
    return TestClient(app), sessions, notifications


def events_of(response):
    """Découpe un flux SSE en liste (événement, données)."""
    out = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def call(name, **arguments):
    return {"function": {"name": name, "arguments": arguments}}


def test_requires_api_key(tmp_path):
    with pytest.raises(ValueError):
        create_app(SessionManager(tmp_path, None, Ollama), "")


def test_health_and_index_are_public(setup):
    client, *_ = setup
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["llm_ready"] is True
    assert health["model"] == "qwen2.5:7b"
    page = client.get("/")
    assert page.status_code == 200 and "Jarvis" in page.text
    assert client.get("/manifest.webmanifest").json()["name"] == "Jarvis"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer mauvaise"},
                                     {"Authorization": KEY}])
def test_api_rejects_bad_keys(setup, headers):
    client, *_ = setup
    for method, path in [("get", "/api/me"), ("get", "/api/tools"),
                         ("post", "/api/conversation/clear"), ("get", "/api/notifications")]:
        assert getattr(client, method)(path, headers=headers).status_code == 401
    assert client.post("/api/chat", json={"message": "x"}, headers=headers).status_code == 401


def test_owner_is_admin_by_default(setup):
    client, *_ = setup
    assert client.get("/api/me", headers=AUTH).json() == {
        "user": "owner", "role": "admin", "name": "Houssen"}
    names = {t["name"] for t in client.get("/api/tools", headers=AUTH).json()["tools"]}
    assert {"executer_commande", "conteneurs_docker", "lire_fichier", "creer_rappel"} <= names


def test_host_users_get_tools_by_role(setup):
    client, sessions, _ = setup
    alice = {**AUTH, "X-Jarvis-User": "42", "X-Jarvis-Name": "Alice", "X-Jarvis-Role": "user"}
    assert client.get("/api/me", headers=alice).json() == {
        "user": "42", "role": "user", "name": "Alice"}
    names = {t["name"] for t in client.get("/api/tools", headers=alice).json()["tools"]}
    assert "infos_systeme" in names and "creer_rappel" in names
    for admin_only in ["executer_commande", "conteneurs_docker", "lire_fichier",
                       "ecrire_fichier", "processus"]:
        assert admin_only not in names
    assert sessions.user_db("42") == sessions.data_dir / "users" / "42" / "memory.db"
    bad = {**AUTH, "X-Jarvis-User": "../etc"}
    assert client.get("/api/me", headers=bad).status_code == 400
    assert client.get("/api/me", headers={**alice, "X-Jarvis-Role": "root"}).status_code == 400


def test_users_have_separate_memory(setup, ollama):
    client, sessions, _ = setup
    bob = {**AUTH, "X-Jarvis-User": "bob"}
    client.post("/api/chat", json={"message": "souviens-toi que j'aime le jazz"}, headers=bob)
    assert "jazz" in str(sessions.get("bob").brain.long_term.get_all())
    assert sessions.get("owner", "admin").brain.long_term.get_all() == {}


def test_chat_streams_tokens_tools_and_done(setup, ollama):
    client, sessions, _ = setup
    ollama.replies += [
        {"content": "", "tool_calls": [call("calculer", expression="6*7")]},
        {"content": "Cela fait 42."},
    ]
    response = client.post("/api/chat", json={"message": "6 fois 7 ?"}, headers=AUTH)
    assert response.headers["content-type"].startswith("text/event-stream")
    events = events_of(response)
    assert events[0] == ("tool", {"name": "calculer", "arguments": {"expression": "6*7"}})
    assert "".join(d["text"] for k, d in events if k == "token") == "Cela fait 42."
    assert events[-1] == ("done", {"response": "Cela fait 42."})
    system = ollama.requests[0]["messages"][0]["content"]
    assert "s'appelle Houssen" in system and "Machine : nexus" in system
    history = client.get("/api/history", headers=AUTH).json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert client.post("/api/conversation/clear", headers=AUTH).json() == {"ok": True}
    assert client.get("/api/history", headers=AUTH).json()["messages"] == []


def test_direct_commands_are_streamed_as_one_token(setup):
    client, *_ = setup
    events = events_of(client.post("/api/chat", json={"message": "calcule 2+2"}, headers=AUTH))
    assert events == [("token", {"text": "2+2 = 4"}), ("done", {"response": "2+2 = 4"})]


@pytest.fixture
def live_server(setup):
    """Vrai serveur uvicorn (le client de test ne diffuse pas le flux au fil de l'eau)."""
    import socket
    import time
    import uvicorn
    client, sessions, notifications = setup
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(client.app, host="127.0.0.1", port=port,
                                           log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.mark.parametrize("approved, expected", [(True, "Code de sortie : 0"),
                                                (False, "Action refusée")])
def test_confirmation_flow(live_server, ollama, approved, expected):
    import httpx
    ollama.replies += [
        {"content": "", "tool_calls": [call("executer_commande", commande="echo bonjour")]},
        {"content": "Terminé."},
    ]
    seen = []
    with httpx.Client(base_url=live_server, timeout=10) as http:
        with http.stream("POST", "/api/chat", json={"message": "Lance echo"},
                         headers=AUTH) as response:
            kind = None
            for line in response.iter_lines():
                if line.startswith("event: "):
                    kind = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                    seen.append(kind)
                    if kind == "confirm":
                        assert data["action"] == "executer_commande(commande='echo bonjour')"
                        intruder = {**AUTH, "X-Jarvis-User": "intrus"}
                        assert http.post("/api/chat/confirm", headers=intruder,
                                         json={"id": data["id"], "approved": True}
                                         ).status_code == 404
                        ok = http.post("/api/chat/confirm", headers=AUTH,
                                       json={"id": data["id"], "approved": approved})
                        assert ok.json() == {"ok": True}
    assert seen == ["tool", "confirm", "token", "done"]
    tool_result = [m for m in ollama.requests[1]["messages"] if m["role"] == "tool"][0]
    assert tool_result["content"].startswith(expected)


def test_tokens_arrive_progressively(live_server, ollama):
    """Le premier morceau arrive avant la fin de la réponse."""
    import httpx
    ollama.replies.append({"content": "un deux trois quatre"})
    with httpx.Client(base_url=live_server, timeout=10) as http:
        with http.stream("POST", "/api/chat", json={"message": "Compte"},
                         headers=AUTH) as response:
            chunks = [c for c in response.iter_raw() if c]
    assert len(chunks) >= 2


def test_unanswered_confirmation_is_refused(setup, ollama, tmp_path):
    client, sessions, notifications = setup
    app = create_app(sessions, KEY, notifications, confirm_timeout=0.2)
    ollama.replies += [
        {"content": "", "tool_calls": [call("executer_commande", commande="reboot")]},
        {"content": "Pas de réponse, j'annule."},
    ]
    TestClient(app).post("/api/chat", json={"message": "Redémarre"}, headers=AUTH)
    tool_result = [m for m in ollama.requests[1]["messages"] if m["role"] == "tool"][0]
    assert tool_result["content"] == "Action refusée par l'utilisateur."


def test_busy_session_returns_409(setup):
    client, sessions, _ = setup
    session = sessions.get("owner", "admin")
    session.lock.acquire()
    try:
        response = client.post("/api/chat", json={"message": "Salut"}, headers=AUTH)
        assert response.status_code == 409
    finally:
        session.lock.release()


def test_errors_are_reported_in_stream(setup, ollama):
    client, sessions, _ = setup
    brain = sessions.get("owner", "admin").brain
    brain.process = lambda *a, **k: 1 / 0
    events = events_of(client.post("/api/chat", json={"message": "x"}, headers=AUTH))
    assert events[-1][0] == "error"
    assert sessions.get("owner", "admin").lock.acquire(blocking=False)


def test_empty_message_rejected(setup):
    client, *_ = setup
    assert client.post("/api/chat", json={"message": ""}, headers=AUTH).status_code == 422


def test_notifications_deliver_due_reminders(setup):
    client, sessions, notifications = setup
    sessions.get("owner", "admin")
    sessions.get("alice", "user")
    TaskStore(sessions.user_db("owner")).add_reminder(
        "Sortir les poubelles", datetime.now() - timedelta(seconds=1))
    TaskStore(sessions.user_db("alice")).add_reminder(
        "Plus tard", datetime.now() + timedelta(hours=1))
    assert notifications.check() == 1
    items = client.get("/api/notifications", headers=AUTH).json()["notifications"]
    assert [n["message"] for n in items] == ["Sortir les poubelles"]
    assert client.get("/api/notifications", headers=AUTH).json()["notifications"] == []


def test_notification_center_thread_and_callback(tmp_path):
    env = Environment("Linux", "6", "h", "u", "/bin/sh", tmp_path, tmp_path, {})
    sessions = SessionManager(tmp_path, env, Ollama)
    TaskStore(sessions.user_db("owner")).add_reminder("Ping", datetime.now())
    got = threading.Event()
    center = NotificationCenter(sessions, interval=0.05, on_notify=lambda n: got.set()).start()
    assert got.wait(2)
    center.stop()
    assert [n.message for n in center.pop("owner")] == ["Ping"]
    assert isinstance(sessions.data_dir, Path)


def test_role_change_keeps_conversation(setup):
    client, sessions, _ = setup
    headers = {**AUTH, "X-Jarvis-User": "carla", "X-Jarvis-Role": "user"}
    client.post("/api/chat", json={"message": "calcule 1+1"}, headers=headers)
    sessions.get("carla", "user").brain.short_term.add("user", "bonjour")
    promoted = sessions.get("carla", "admin")
    assert promoted.role == "admin" and "executer_commande" in promoted.brain.tools
    assert promoted.brain.short_term.count() == 1


# ─────────────────────────────────────────────
# Étape 7 : clés d'application, autorisations, API OpenAI
# ─────────────────────────────────────────────

from core.clients import ClientStore  # noqa: E402


@pytest.fixture
def multi(ollama, tmp_path):
    env = Environment(os_name="Linux", os_version="6", hostname="nexus", user="srv",
                      shell="/bin/bash", cwd=tmp_path, workspace=tmp_path,
                      programs={"conteneurs": ["docker"]})
    sessions = SessionManager(tmp_path / "data", env,
                              lambda: Ollama(host=ollama.url, model="qwen2.5:7b"))
    notifications = NotificationCenter(sessions)
    clients = ClientStore(tmp_path / "data" / "clients.db")
    keys = {
        "phone": clients.add("telephone"),
        "guest": clients.add("invite", role="user", user="invite"),
        "nexus": clients.add("nexus", role="admin", trusted=True),
        "limited": clients.add("partenaire", role="user", trusted=True),
    }
    app = create_app(sessions, KEY, notifications, owner_name="Houssen", clients=clients)
    return TestClient(app), keys, sessions


def bearer(key, **extra):
    return {"Authorization": f"Bearer {key}", **extra}


def test_app_keys_identity_and_roles(multi):
    client, keys, _ = multi
    assert client.get("/api/me", headers=bearer(keys["phone"])).json() == \
        {"user": "owner", "role": "admin", "name": "Houssen"}
    assert client.get("/api/me", headers=bearer(keys["guest"])).json() == \
        {"user": "invite", "role": "user", "name": "invite"}
    # Une clé sans « confiance » ne parle pas au nom des autres
    assert client.get("/api/me", headers=bearer(keys["phone"], **{"X-Jarvis-User": "42"})
                      ).status_code == 403
    # Nexus (confiance, admin) parle au nom de ses utilisateurs
    alice = bearer(keys["nexus"], **{"X-Jarvis-User": "42", "X-Jarvis-Name": "Alice",
                                     "X-Jarvis-Role": "admin"})
    assert client.get("/api/me", headers=alice).json() == \
        {"user": "42", "role": "admin", "name": "Alice"}
    # Le rôle demandé ne dépasse jamais celui de la clé
    capped = bearer(keys["limited"], **{"X-Jarvis-User": "7", "X-Jarvis-Role": "admin"})
    assert client.get("/api/me", headers=capped).json()["role"] == "user"


def test_revoked_key_stops_working(multi, tmp_path):
    client, keys, sessions = multi
    ClientStore(tmp_path / "data" / "clients.db").remove("telephone")
    assert client.get("/api/me", headers=bearer(keys["phone"])).status_code == 401


def test_openai_models_and_auth(multi):
    client, keys, _ = multi
    assert client.get("/v1/models").status_code == 401
    data = client.get("/v1/models", headers=bearer(keys["phone"])).json()
    assert data["data"][0]["id"] == "jarvis"


def test_openai_chat_non_stream_is_stateless(multi, ollama):
    client, keys, sessions = multi
    ollama.replies.append({"content": "Bonjour Houssen !"})
    body = {"model": "jarvis", "temperature": 0.2, "messages": [
        {"role": "system", "content": "Tu es un pirate."},
        {"role": "user", "content": "Salut"},
        {"role": "assistant", "content": "Salut !"},
        {"role": "user", "content": [{"type": "text", "text": "Ça va ?"}]},
    ]}
    data = client.post("/v1/chat/completions", json=body, headers=bearer(keys["phone"])).json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"] == {"role": "assistant", "content": "Bonjour Houssen !"}
    sent = ollama.requests[0]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert "pirate" not in sent[0]["content"] and sent[-1]["content"] == "Ça va ?"
    # La conversation de la page web n'est pas modifiée
    assert sessions.get("owner", "admin").brain.short_term.count() == 0


def test_openai_chat_stream_format(multi, ollama):
    client, keys, _ = multi
    ollama.replies.append({"content": "un deux trois"})
    body = {"messages": [{"role": "user", "content": "Compte"}], "stream": True}
    text = client.post("/v1/chat/completions", json=body, headers=bearer(keys["phone"])).text
    lines = [line[6:] for line in text.split("\n") if line.startswith("data: ")]
    assert lines[-1] == "[DONE]"
    chunks = [json.loads(line) for line in lines[:-1]]
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant"}
    content = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    assert content == "un deux trois"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert all(c["object"] == "chat.completion.chunk" for c in chunks)


def test_openai_rejects_bad_conversations(multi):
    client, keys, _ = multi
    for messages in [[], [{"role": "assistant", "content": "x"}],
                     [{"role": "user", "content": "  "}]]:
        response = client.post("/v1/chat/completions", json={"messages": messages},
                               headers=bearer(keys["phone"]))
        assert response.status_code == 400


def test_sensitive_action_from_openai_waits_for_approval(multi, ollama):
    client, keys, sessions = multi
    ollama.replies += [
        {"content": "", "tool_calls": [call("executer_commande", commande="echo prêt")]},
        {"content": "J'attends ton autorisation."},
    ]
    body = {"messages": [{"role": "user", "content": "Lance echo prêt"}]}
    answer = client.post("/v1/chat/completions", json=body, headers=bearer(keys["phone"]))
    assert answer.json()["choices"][0]["message"]["content"] == "J'attends ton autorisation."
    tool_msg = [m for m in ollama.requests[1]["messages"] if m["role"] == "tool"][0]
    assert "mise en attente" in tool_msg["content"]

    owner = bearer(keys["phone"])
    pending = client.get("/api/approvals", headers=owner).json()["approvals"]
    assert [(a["action"], a["source"]) for a in pending] == \
        [("executer_commande(commande='echo prêt')", "telephone")]
    # Un autre utilisateur ne voit pas et ne peut pas autoriser
    guest = bearer(keys["guest"])
    assert client.get("/api/approvals", headers=guest).json()["approvals"] == []
    assert client.post(f"/api/approvals/{pending[0]['id']}", json={"approved": True},
                       headers=guest).status_code == 404

    decided = client.post(f"/api/approvals/{pending[0]['id']}", json={"approved": True},
                          headers=owner).json()
    assert decided["approved"] is True and "prêt" in decided["result"]
    kinds = [(n["kind"], n["message"].split(" ")[0])
             for n in client.get("/api/notifications", headers=owner).json()["notifications"]]
    assert kinds == [("info", "Autorisation"), ("info", "Action")]
    assert client.get("/api/approvals", headers=owner).json()["approvals"] == []


# ─────────────────────────────────────────────
# Étape 8 : notifications push, fichiers de la PWA
# ─────────────────────────────────────────────

from core.push import PushService, PushStore, VapidKeys  # noqa: E402
from tests.test_push import browser_decrypt, browser_keys  # noqa: E402


@pytest.fixture
def with_push(ollama, tmp_path):
    env = Environment("Linux", "6", "h", "u", "/bin/sh", tmp_path, tmp_path, {})
    sessions = SessionManager(tmp_path / "data", env,
                              lambda: Ollama(host=ollama.url, model="qwen2.5:7b"))
    notifications = NotificationCenter(sessions)
    sent = []
    push = PushService(PushStore(tmp_path / "push.db"),
                       VapidKeys.load_or_create(tmp_path / "vapid.pem"),
                       "mailto:jarvis@example.com",
                       post=lambda url, body, headers: sent.append((url, body)) or 201)
    app = create_app(sessions, KEY, notifications, push=push)
    return TestClient(app), push, notifications, sent


def test_pwa_files(setup):
    client, *_ = setup
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    assert "showNotification" in sw.text
    icon = client.get("/icons/icon-192.png")
    assert icon.status_code == 200 and icon.content[:4] == b"\x89PNG"
    assert client.get("/icons/inconnu.png").status_code == 404
    assert client.get("/icons/..%2Fserver.py").status_code == 404
    manifest = client.get("/manifest.webmanifest").json()
    assert {i["sizes"] for i in manifest["icons"]} == {"192x192", "512x512"}


def test_push_disabled_without_service(setup):
    client, *_ = setup
    assert client.get("/api/push/key", headers=AUTH).json() == {"publicKey": None}
    _, p256dh, auth = browser_keys()
    body = {"endpoint": "https://fcm.googleapis.com/x", "keys": {"p256dh": p256dh, "auth": auth}}
    assert client.post("/api/push/subscribe", json=body, headers=AUTH).status_code == 503


def test_push_subscribe_test_and_reminders(with_push):
    client, push, notifications, sent = with_push
    assert client.get("/api/push/key").status_code == 401
    assert client.get("/api/push/key", headers=AUTH).json()["publicKey"] == push.keys.public_key

    private, p256dh, auth = browser_keys()
    body = {"endpoint": "https://web.push.apple.com/abc", "expirationTime": None,
            "keys": {"p256dh": p256dh, "auth": auth}}
    assert client.post("/api/push/subscribe", json=body, headers=AUTH).json() == {"ok": True}
    bad = {**body, "endpoint": "https://192.168.1.10/vol"}
    assert client.post("/api/push/subscribe", json=bad, headers=AUTH).status_code == 400

    assert client.post("/api/push/test", headers=AUTH).json() == {"sent": 1}
    assert json.loads(browser_decrypt(sent[-1][1], private, auth))["tag"] == "test"

    # Un rappel échu part aussi en notification push (en arrière-plan)
    notifications.push("owner", "Autorisation demandée (#3) : redemarrer_conteneur(nom='a')")
    for _ in range(100):
        if len(sent) >= 2:
            break
        time.sleep(0.02)
    payload = json.loads(browser_decrypt(sent[-1][1], private, auth))
    assert payload["title"] == "Jarvis demande une autorisation"

    assert client.post("/api/push/unsubscribe", json={"endpoint": body["endpoint"]},
                       headers=AUTH).json() == {"ok": True}
    assert client.post("/api/push/test", headers=AUTH).json() == {"sent": 0}
