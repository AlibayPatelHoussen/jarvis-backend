"""
core/push.py
============
Notifications push (Web Push) : rappels et demandes d'autorisation
arrivent sur le téléphone même quand la page Jarvis est fermée.

Gratuit et sans compte : le navigateur (Safari, Chrome, Firefox) fournit
une adresse d'abonnement ; Jarvis y envoie un message chiffré que seul
ce navigateur peut lire.

Implémentation des standards, avec la seule bibliothèque `cryptography` :
- VAPID (RFC 8292) : Jarvis signe ses envois avec sa propre clé,
  générée au premier démarrage (DATA_DIR/vapid_private.pem) ;
- chiffrement « aes128gcm » (RFC 8291 + RFC 8188).

Sur iPhone : les notifications web ne fonctionnent que si la page est
ajoutée à l'écran d'accueil (iOS 16.4 ou plus récent).
"""

import base64
import json
import logging
import os
import sqlite3
import struct
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("jarvis.push")

# Services de push des navigateurs. Jarvis n'envoie qu'à ces adresses :
# un client ne peut pas lui faire appeler une machine arbitraire.
PUSH_HOSTS = (
    "fcm.googleapis.com",               # Chrome, Edge, Android
    "updates.push.services.mozilla.com",  # Firefox
    "push.apple.com",                   # Safari (macOS, iPhone)
    "notify.windows.com",               # Edge (Windows)
)
RECORD_SIZE = 4096


class PushError(ValueError):
    pass


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _hmac(key: bytes, data: bytes) -> bytes:
    h = hmac.HMAC(key, hashes.SHA256())
    h.update(data)
    return h.finalize()


def _public_bytes(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.X962,
                            serialization.PublicFormat.UncompressedPoint)


# ─────────────────────────────────────────────
# Clés VAPID
# ─────────────────────────────────────────────

class VapidKeys:
    def __init__(self, private_key: ec.EllipticCurvePrivateKey):
        self.private_key = private_key

    @classmethod
    def load_or_create(cls, path: Path) -> "VapidKeys":
        path = Path(path)
        if path.exists():
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
            return cls(key)
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
        return cls(key)

    @property
    def public_key(self) -> str:
        """Clé publique (base64url) à donner au navigateur."""
        return b64url(_public_bytes(self.private_key.public_key()))

    def authorization(self, endpoint: str, subject: str, ttl: int = 12 * 3600) -> str:
        """En-tête Authorization VAPID (jeton JWT ES256)."""
        url = urlparse(endpoint)
        header = b64url(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
        claims = b64url(json.dumps({
            "aud": f"{url.scheme}://{url.netloc}",
            "exp": int(time.time()) + ttl,
            "sub": subject,
        }).encode())
        signing_input = f"{header}.{claims}".encode()
        der = self.private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        signature = b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        return f"vapid t={header}.{claims}.{signature}, k={self.public_key}"


# ─────────────────────────────────────────────
# Chiffrement (RFC 8291, aes128gcm)
# ─────────────────────────────────────────────

def encrypt(payload: bytes, p256dh: str, auth: str,
            salt: Optional[bytes] = None,
            server_key: Optional[ec.EllipticCurvePrivateKey] = None) -> bytes:
    """
    Chiffre `payload` pour un abonnement (clés p256dh et auth du navigateur).

    salt et server_key ne servent qu'aux tests (valeurs fixes).
    """
    ua_public = b64url_decode(p256dh)
    auth_secret = b64url_decode(auth)
    if len(ua_public) != 65 or len(auth_secret) != 16:
        raise PushError("clés d'abonnement invalides")
    if len(payload) > RECORD_SIZE - 17 - 86:
        raise PushError("message trop long pour une notification")

    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_public = _public_bytes(server_key.public_key())
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = server_key.exchange(ec.ECDH(), ua_key)

    # IKM = HKDF(auth_secret, ecdh_secret, "WebPush: info" || 0 || ua_public || as_public)
    prk_key = _hmac(auth_secret, shared)
    ikm = _hmac(prk_key, b"WebPush: info\x00" + ua_public + as_public + b"\x01")
    salt = salt or os.urandom(16)
    prk = _hmac(salt, ikm)
    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]

    ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    header = salt + struct.pack("!IB", RECORD_SIZE, len(as_public)) + as_public
    return header + ciphertext


# ─────────────────────────────────────────────
# Abonnements
# ─────────────────────────────────────────────

def check_endpoint(endpoint: str) -> None:
    url = urlparse(endpoint or "")
    host = (url.hostname or "").lower()
    if url.scheme != "https" or not any(host == h or host.endswith("." + h)
                                        for h in PUSH_HOSTS):
        raise PushError("adresse d'abonnement refusée (service de push inconnu)")


class PushStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    endpoint   TEXT PRIMARY KEY,
                    user_id    TEXT NOT NULL,
                    p256dh     TEXT NOT NULL,
                    auth       TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def add(self, user_id: str, endpoint: str, p256dh: str, auth: str) -> None:
        check_endpoint(endpoint)
        try:
            ok = len(b64url_decode(p256dh)) == 65 and len(b64url_decode(auth)) == 16
        except (ValueError, TypeError):
            ok = False
        if not ok:
            raise PushError("clés d'abonnement invalides")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO subscriptions (endpoint, user_id, p256dh, auth, created_at)"
                " VALUES (?, ?, ?, ?, ?) ON CONFLICT(endpoint) DO UPDATE SET"
                " user_id = excluded.user_id, p256dh = excluded.p256dh, auth = excluded.auth",
                (endpoint, user_id, p256dh, auth, datetime.now().isoformat(timespec="seconds")),
            )

    def remove(self, endpoint: str, user_id: Optional[str] = None) -> bool:
        query, params = "DELETE FROM subscriptions WHERE endpoint = ?", [endpoint]
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        with self._connect() as conn:
            return conn.execute(query, params).rowcount > 0

    def for_user(self, user_id: str) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM subscriptions WHERE user_id = ?", (user_id,))]


# ─────────────────────────────────────────────
# Envoi
# ─────────────────────────────────────────────

def _post(url: str, body: bytes, headers: dict, timeout: float = 10) -> int:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


class PushService:
    """Envoie des notifications à tous les appareils abonnés d'un utilisateur."""

    def __init__(self, store: PushStore, keys: VapidKeys, subject: str, post=_post):
        self.store = store
        self.keys = keys
        self.subject = subject
        self._post = post

    def send(self, user_id: str, title: str, body: str, url: str = "/",
             tag: Optional[str] = None) -> int:
        """Retourne le nombre d'appareils prévenus."""
        payload = json.dumps({"title": title, "body": body[:400], "url": url,
                              "tag": tag}, ensure_ascii=False).encode("utf-8")
        delivered = 0
        for sub in self.store.for_user(user_id):
            try:
                data = encrypt(payload, sub["p256dh"], sub["auth"])
                status = self._post(sub["endpoint"], data, {
                    "Authorization": self.keys.authorization(sub["endpoint"], self.subject),
                    "Content-Encoding": "aes128gcm",
                    "Content-Type": "application/octet-stream",
                    "TTL": "86400",
                    "Urgency": "high",
                })
            except Exception as e:
                logger.warning(f"[Push] Échec d'envoi : {e}")
                continue
            if status in (404, 410):  # abonnement expiré ou retiré
                self.store.remove(sub["endpoint"])
            elif 200 <= status < 300:
                delivered += 1
            else:
                logger.warning(f"[Push] Le service de push a répondu {status}")
        return delivered
