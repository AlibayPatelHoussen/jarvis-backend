"""
api/server.py
=============
Jarvis en mode serveur : une API HTTP + une page de chat web.

Lancement :
    python start.py --server            (ou : python -m api)

Sécurité :
- Toutes les routes /api/* exigent la clé JARVIS_API_KEY
  (en-tête « Authorization: Bearer <clé> »). Sans clé configurée,
  le serveur refuse de démarrer.
- Par défaut le serveur n'écoute qu'en local (127.0.0.1) : on l'expose
  au monde via un tunnel HTTPS (Cloudflare) ou un reverse proxy.

Identité :
- Sans en-tête particulier, la requête vient du propriétaire
  (utilisateur "owner", rôle admin).
- Une application de confiance qui possède la clé (Nexus plus tard)
  peut parler au nom de ses utilisateurs avec les en-têtes
  X-Jarvis-User, X-Jarvis-Name et X-Jarvis-Role (admin | user).

La référence complète de l'API est dans docs/API.md.
"""

import hmac
import json
import logging
import queue
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from config import settings
from core.approvals import ApprovalCenter
from core.clients import ClientStore
from core.push import PushError, PushService, PushStore, VapidKeys
from core.sessions import NotificationCenter, Session, SessionError, SessionManager

logger = logging.getLogger("jarvis.api")

STATIC_DIR = Path(__file__).parent / "static"
VERSION = "1.0.0"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)


class ConfirmRequest(BaseModel):
    id: str
    approved: bool


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    """Abonnement fourni par le navigateur (PushSubscription.toJSON())."""
    model_config = ConfigDict(extra="ignore")
    endpoint: str
    keys: PushKeys


class PushEndpoint(BaseModel):
    endpoint: str


def _push_title(kind: str, message: str) -> tuple[str, str]:
    """Titre et étiquette d'une notification push."""
    if kind == "reminder":
        return "⏰ Rappel", "rappel"
    if message.startswith("Autorisation demandée"):
        return "Jarvis demande une autorisation", "autorisation"
    return "Jarvis", "info"


class DecisionRequest(BaseModel):
    approved: bool


class OpenAIChatRequest(BaseModel):
    """Requête au format OpenAI (les champs inconnus sont ignorés)."""
    model_config = ConfigDict(extra="ignore")
    model: str = "jarvis"
    messages: list[dict]
    stream: bool = False


@dataclass
class Caller:
    """Qui appelle : la session de l'utilisateur et l'application."""
    session: Session
    client: str


def _text_of(content) -> str:
    """Contenu d'un message OpenAI : texte simple ou liste de morceaux."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def openai_to_jarvis(messages: list[dict]) -> tuple[list[dict], str]:
    """
    Convertit une conversation OpenAI en (historique, dernier message).

    Les messages "system" de l'application sont ignorés : Jarvis garde
    sa propre personnalité et ses consignes de sécurité.
    """
    turns = [{"role": m.get("role"), "content": _text_of(m.get("content"))}
             for m in messages if m.get("role") in ("user", "assistant")]
    if not turns or turns[-1]["role"] != "user" or not turns[-1]["content"].strip():
        raise HTTPException(status_code=400,
                            detail="Le dernier message doit venir de l'utilisateur.")
    return turns[:-1][-20:], turns[-1]["content"]


class _PendingConfirm:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.event = threading.Event()
        self.approved = False


def create_app(
    sessions: SessionManager,
    api_key: str,
    notifications: Optional[NotificationCenter] = None,
    confirm_timeout: float = 120.0,
    owner_name: str = "",
    background: bool = False,
    clients: Optional[ClientStore] = None,
    approvals: Optional[ApprovalCenter] = None,
    push: Optional[PushService] = None,
) -> FastAPI:
    """
    Construit l'application (paramétrable pour les tests).

    Args:
        api_key    : clé principale (propriétaire, admin)
        clients    : clés par application (python start.py cles …)
        approvals  : actions sensibles en attente d'autorisation
        push       : notifications push vers les téléphones / navigateurs
        background : True pour lancer la vérification des rappels
                     pendant que le serveur tourne.
    """
    if approvals is None:
        approvals = ApprovalCenter(notify=notifications.push if notifications else None)
    if push and notifications and notifications.on_notify is None:
        def send_push(note):
            title, tag = _push_title(note.kind, note.message)
            # Envoi en arrière-plan : ne jamais bloquer les rappels ni le chat
            threading.Thread(target=push.send, name="jarvis-push", daemon=True,
                             args=(note.user_id, title, note.message, "/", tag)).start()
        notifications.on_notify = send_push
    if not api_key:
        raise ValueError("JARVIS_API_KEY est vide : le serveur refuse de démarrer sans clé.")

    @asynccontextmanager
    async def lifespan(_app):
        if background and notifications:
            notifications.start()
        yield
        if background and notifications:
            notifications.stop()

    app = FastAPI(title="Jarvis", version=VERSION, docs_url=None, redoc_url=None,
                  lifespan=lifespan)
    pending: dict[str, _PendingConfirm] = {}
    pending_lock = threading.Lock()

    # ─────────────────────────────────────────
    # Authentification et identité
    # ─────────────────────────────────────────

    def caller_for(
        authorization: str = Header(default=""),
        x_jarvis_user: str = Header(default=""),
        x_jarvis_name: str = Header(default=""),
        x_jarvis_role: str = Header(default=""),
    ) -> Caller:
        token = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
        if token and hmac.compare_digest(token.encode(), api_key.encode()):
            client, max_role, trusted, user = "principal", "admin", True, "owner"
        else:
            app_client = clients.authenticate(token) if (clients and token) else None
            if app_client is None:
                raise HTTPException(status_code=401, detail="Clé d'accès invalide.")
            client, max_role = app_client.name, app_client.role
            trusted, user = app_client.trusted, app_client.user

        role, name = max_role, (owner_name if user == "owner" else "")
        if x_jarvis_user:
            if not trusted:
                raise HTTPException(
                    status_code=403,
                    detail="Cette clé ne peut pas parler au nom d'autres utilisateurs.")
            user, name = x_jarvis_user, x_jarvis_name
            requested = x_jarvis_role or "user"
            if requested not in ("admin", "user"):
                raise HTTPException(status_code=400, detail=f"rôle invalide : {requested!r}")
            # Le rôle demandé ne dépasse jamais celui de la clé
            role = "admin" if (requested == "admin" and max_role == "admin") else "user"
        try:
            return Caller(sessions.get(user, role, name), client)
        except SessionError as e:
            raise HTTPException(status_code=400, detail=str(e))

    def session_for(caller: Caller = Depends(caller_for)) -> Session:
        return caller.session

    # ─────────────────────────────────────────
    # Routes publiques
    # ─────────────────────────────────────────

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(STATIC_DIR / "manifest.webmanifest",
                            media_type="application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        return FileResponse(STATIC_DIR / "sw.js", media_type="text/javascript",
                            headers={"Cache-Control": "no-cache"})

    @app.get("/icons/{name}", include_in_schema=False)
    def icons(name: str):
        path = STATIC_DIR / "icons" / name
        if "/" in name or ".." in name or not path.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(path, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/health")
    def health():
        """État du service (sans clé : pour la supervision)."""
        llm = sessions.llm_factory()
        warning = None
        if not llm.is_available():
            warning = "Ollama n'est pas accessible."
        elif not llm.has_model():
            warning = f"Le modèle '{llm.model}' n'est pas installé."
        return {"status": "ok", "version": VERSION, "model": llm.model,
                "llm_ready": warning is None, "warning": warning}

    # ─────────────────────────────────────────
    # Routes protégées
    # ─────────────────────────────────────────

    @app.get("/api/me")
    def me(session: Session = Depends(session_for)):
        return {"user": session.user_id, "role": session.role,
                "name": session.brain.user_name}

    @app.get("/api/tools")
    def tools(session: Session = Depends(session_for)):
        registry = session.brain.tools
        return {"tools": [
            {"name": name, "description": registry.get(name).description,
             "confirm": registry.get(name).confirm}
            for name in registry.names()
        ]}

    @app.get("/api/history")
    def history(session: Session = Depends(session_for)):
        return {"messages": session.brain.short_term.get_history()}

    @app.post("/api/conversation/clear")
    def clear(session: Session = Depends(session_for)):
        session.brain.clear_conversation()
        return {"ok": True}

    @app.get("/api/notifications")
    def get_notifications(session: Session = Depends(session_for)):
        items = notifications.pop(session.user_id) if notifications else []
        return {"notifications": [
            {"id": n.id, "kind": n.kind, "message": n.message,
             "due_at": n.due_at.isoformat()}
            for n in items
        ]}

    @app.get("/api/push/key")
    def push_key(session: Session = Depends(session_for)):
        """Clé publique VAPID pour s'abonner (null si le push est désactivé)."""
        return {"publicKey": push.keys.public_key if push else None}

    @app.post("/api/push/subscribe")
    def push_subscribe(body: PushSubscription, session: Session = Depends(session_for)):
        if not push:
            raise HTTPException(status_code=503, detail="Notifications push désactivées.")
        try:
            push.store.add(session.user_id, body.endpoint, body.keys.p256dh, body.keys.auth)
        except PushError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    @app.post("/api/push/unsubscribe")
    def push_unsubscribe(body: PushEndpoint, session: Session = Depends(session_for)):
        removed = push.store.remove(body.endpoint, session.user_id) if push else False
        return {"ok": removed}

    @app.post("/api/push/test")
    def push_test(session: Session = Depends(session_for)):
        if not push:
            raise HTTPException(status_code=503, detail="Notifications push désactivées.")
        sent = push.send(session.user_id, "Jarvis",
                         "Les notifications fonctionnent sur cet appareil.", tag="test")
        return {"sent": sent}

    @app.get("/api/approvals")
    def list_approvals(session: Session = Depends(session_for)):
        """Actions sensibles en attente d'autorisation."""
        return {"approvals": [
            {"id": a.id, "action": a.action, "source": a.source,
             "created": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(a.created))}
            for a in approvals.pending(session.user_id)
        ]}

    @app.post("/api/approvals/{approval_id}")
    def decide_approval(approval_id: int, body: DecisionRequest,
                        session: Session = Depends(session_for)):
        """Autorise (exécute) ou refuse une action en attente."""
        result = approvals.decide(approval_id, session.user_id, body.approved)
        if result is None:
            raise HTTPException(status_code=404, detail="Demande inconnue ou expirée.")
        return {"approved": body.approved, "result": result}

    # ─────────────────────────────────────────
    # API au format standard (OpenAI)
    # ─────────────────────────────────────────
    # Seulement le FORMAT des messages : aucun compte ni service OpenAI
    # n'est utilisé, c'est ce serveur (modèle local Ollama) qui répond.
    # N'importe quelle application qui accepte « une adresse OpenAI
    # personnalisée » peut parler à Jarvis : base_url = https://…/v1,
    # clé = une clé d'application, modèle = "jarvis". Les actions
    # sensibles sont mises en attente (pas d'écran de confirmation).

    @app.get("/v1/models")
    def openai_models(caller: Caller = Depends(caller_for)):
        return {"object": "list", "data": [
            {"id": "jarvis", "object": "model", "created": 0, "owned_by": "jarvis"}]}

    @app.post("/v1/chat/completions")
    def openai_chat(body: OpenAIChatRequest, caller: Caller = Depends(caller_for)):
        history, message = openai_to_jarvis(body.messages)
        session = caller.session
        # Les applications OpenAI attendent une réponse : on patiente un peu
        if not session.lock.acquire(timeout=60):
            raise HTTPException(status_code=409,
                                detail="Jarvis répond déjà à un autre message.")
        brain = session.brain
        completion_id = "chatcmpl-" + uuid.uuid4().hex[:24]
        created = int(time.time())

        def run(on_token=None) -> str:
            brain.confirm = approvals.deferred_confirm(session.user_id, source=caller.client)
            brain.on_tool = None
            try:
                return brain.process(message, on_token=on_token, history=history)
            finally:
                brain.confirm = None

        if not body.stream:
            try:
                response = run()
            finally:
                session.lock.release()
            return {
                "id": completion_id, "object": "chat.completion", "created": created,
                "model": "jarvis",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": response}}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }

        chunks: queue.Queue = queue.Queue()

        def chunk(delta: dict, finish=None) -> str:
            data = {"id": completion_id, "object": "chat.completion.chunk",
                    "created": created, "model": "jarvis",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        def work():
            try:
                streamed = []

                def on_token(text: str) -> None:
                    streamed.append(text)
                    chunks.put(chunk({"content": text}))

                response = run(on_token)
                if not streamed and response:
                    chunks.put(chunk({"content": response}))
            except Exception as e:
                logger.exception("Erreur pendant une requête OpenAI")
                chunks.put(chunk({"content": f"Erreur interne : {e}"}))
            finally:
                session.lock.release()
                chunks.put(chunk({}, finish="stop"))
                chunks.put("data: [DONE]\n\n")
                chunks.put(None)

        threading.Thread(target=work, name="jarvis-openai", daemon=True).start()
        chunks.put(chunk({"role": "assistant"}))

        def stream():
            while True:
                item = chunks.get()
                if item is None:
                    return
                yield item

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    @app.post("/api/chat/confirm")
    def confirm(body: ConfirmRequest, session: Session = Depends(session_for)):
        with pending_lock:
            item = pending.get(body.id)
        if item is None or item.user_id != session.user_id:
            raise HTTPException(status_code=404, detail="Demande de confirmation inconnue.")
        item.approved = body.approved
        item.event.set()
        return {"ok": True}

    @app.post("/api/chat")
    def chat(body: ChatRequest, request: Request, session: Session = Depends(session_for)):
        """
        Envoie un message. Réponse en flux SSE (text/event-stream) :
          token   {"text"}                  morceau de la réponse
          tool    {"name", "arguments"}     outil utilisé
          confirm {"id", "action"}          autorisation demandée
                                            → POST /api/chat/confirm
          done    {"response"}              réponse complète
          error   {"message"}
        """
        if not session.lock.acquire(blocking=False):
            raise HTTPException(status_code=409,
                                detail="Jarvis répond déjà à un autre message.")
        events: queue.Queue = queue.Queue()
        brain = session.brain

        def ask_confirmation(action: str) -> bool:
            confirm_id = uuid.uuid4().hex
            item = _PendingConfirm(session.user_id)
            with pending_lock:
                pending[confirm_id] = item
            events.put(("confirm", {"id": confirm_id, "action": action}))
            answered = item.event.wait(confirm_timeout)
            with pending_lock:
                pending.pop(confirm_id, None)
            return answered and item.approved

        def work():
            try:
                brain.confirm = ask_confirmation
                brain.on_tool = lambda name, args: events.put(
                    ("tool", {"name": name, "arguments": args}))
                streamed = []

                def on_token(text: str) -> None:
                    streamed.append(text)
                    events.put(("token", {"text": text}))

                response = brain.process(body.message, on_token=on_token)
                if not streamed and response:
                    events.put(("token", {"text": response}))
                events.put(("done", {"response": response}))
            except Exception as e:  # ne jamais laisser le flux sans fin
                logger.exception("Erreur pendant le traitement d'un message")
                events.put(("error", {"message": f"Erreur interne : {e}"}))
            finally:
                brain.confirm = None
                brain.on_tool = None
                session.lock.release()
                events.put(None)

        threading.Thread(target=work, name="jarvis-chat", daemon=True).start()

        def stream():
            while True:
                item = events.get()
                if item is None:
                    return
                kind, data = item
                yield f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    return app


def build_default_app() -> FastAPI:
    """Application configurée depuis .env (utilisée par start.py --server)."""
    from core.environment import discover
    from llm.ollama import Ollama

    sessions = SessionManager(settings.DATA_DIR, discover(settings.WORKSPACE), Ollama)
    return create_app(sessions, settings.API_KEY, NotificationCenter(sessions),
                      confirm_timeout=settings.CONFIRM_TIMEOUT,
                      owner_name=settings.USER_NAME, background=True,
                      clients=ClientStore(settings.DATA_DIR / "clients.db"),
                      push=PushService(PushStore(settings.DATA_DIR / "push.db"),
                                       VapidKeys.load_or_create(
                                           settings.DATA_DIR / "vapid_private.pem"),
                                       settings.PUSH_CONTACT))


def run(host: str = None, port: int = None) -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not settings.API_KEY:
        print("ERREUR : JARVIS_API_KEY n'est pas définie dans .env.")
        print("Générez-en une : python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
        raise SystemExit(1)
    uvicorn.run(build_default_app(), host=host or settings.SERVER_HOST,
                port=port or settings.SERVER_PORT, log_level="info")
