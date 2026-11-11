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
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from config import settings
from core.sessions import NotificationCenter, Session, SessionError, SessionManager

logger = logging.getLogger("jarvis.api")

STATIC_DIR = Path(__file__).parent / "static"
VERSION = "1.0.0"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)


class ConfirmRequest(BaseModel):
    id: str
    approved: bool


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
) -> FastAPI:
    """
    Construit l'application (paramétrable pour les tests).

    Args:
        background : True pour lancer la vérification des rappels
                     pendant que le serveur tourne.
    """
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

    def session_for(
        authorization: str = Header(default=""),
        x_jarvis_user: str = Header(default=""),
        x_jarvis_name: str = Header(default=""),
        x_jarvis_role: str = Header(default=""),
    ) -> Session:
        token = authorization[7:] if authorization.startswith("Bearer ") else ""
        if not token or not hmac.compare_digest(token.encode(), api_key.encode()):
            raise HTTPException(status_code=401, detail="Clé d'accès invalide.")
        try:
            if x_jarvis_user:
                return sessions.get(x_jarvis_user, x_jarvis_role or "user", x_jarvis_name)
            return sessions.get("owner", "admin", owner_name)
        except SessionError as e:
            raise HTTPException(status_code=400, detail=str(e))

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
            {"id": n.id, "message": n.message, "due_at": n.due_at.isoformat()}
            for n in items
        ]}

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
                      owner_name=settings.USER_NAME, background=True)


def run(host: str = None, port: int = None) -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not settings.API_KEY:
        print("ERREUR : JARVIS_API_KEY n'est pas définie dans .env.")
        print("Générez-en une : python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
        raise SystemExit(1)
    uvicorn.run(build_default_app(), host=host or settings.SERVER_HOST,
                port=port or settings.SERVER_PORT, log_level="info")
