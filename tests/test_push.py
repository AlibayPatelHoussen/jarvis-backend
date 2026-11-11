"""
tests/test_push.py
==================
Tests unitaires pour core/push.py (notifications push Web Push)
"""

import json
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.push import (
    PushError, PushService, PushStore, VapidKeys, b64url, b64url_decode, check_endpoint,
    encrypt,
)

ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"


def browser_keys():
    """Clés d'un navigateur simulé : (clé privée, p256dh, auth)."""
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key().public_bytes(serialization.Encoding.X962,
                                               serialization.PublicFormat.UncompressedPoint)
    return private, b64url(public), b64url(b"0123456789abcdef")


def browser_decrypt(data: bytes, private, auth: str) -> bytes:
    """Déchiffrement côté navigateur (RFC 8291), écrit indépendamment."""
    from cryptography.hazmat.primitives import hmac as h

    def mac(key, msg):
        m = h.HMAC(key, hashes.SHA256())
        m.update(msg)
        return m.finalize()

    salt, idlen = data[:16], data[20]
    as_public = data[21:21 + idlen]
    ua_public = private.public_key().public_bytes(serialization.Encoding.X962,
                                                  serialization.PublicFormat.UncompressedPoint)
    shared = private.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), as_public))
    ikm = mac(mac(b64url_decode(auth), shared),
              b"WebPush: info\x00" + ua_public + as_public + b"\x01")
    prk = mac(salt, ikm)
    cek = mac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = mac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    plain = AESGCM(cek).decrypt(nonce, data[21 + idlen:], None)
    assert plain.endswith(b"\x02")
    return plain[:-1]


def test_rfc8291_test_vector():
    """Exemple officiel de la RFC 8291 (annexe A) : octet pour octet."""
    as_private = ec.derive_private_key(int.from_bytes(
        b64url_decode("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"), ec.SECP256R1())
    out = encrypt(
        b"When I grow up, I want to be a watermelon",
        p256dh="BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkN"
               "toIAiw4",
        auth="BTBZMqHH6r4Tts7J_aSIgg",
        salt=b64url_decode("DGv6ra1nlYgDCS1FRnbzlw"),
        server_key=as_private,
    )
    assert b64url(out) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocIn"
        "mYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNW"
        "QexSgSxsj_Qulcy4a-fN")


def test_encrypt_roundtrip_with_random_keys():
    private, p256dh, auth = browser_keys()
    message = json.dumps({"title": "⏰ Rappel", "body": "Appeler maman"}).encode()
    assert browser_decrypt(encrypt(message, p256dh, auth), private, auth) == message


def test_encrypt_rejects_bad_input():
    _, p256dh, auth = browser_keys()
    with pytest.raises(PushError):
        encrypt(b"x", "AAAA", auth)
    with pytest.raises(PushError):
        encrypt(b"x" * 5000, p256dh, auth)


def test_vapid_keys_persist_and_sign(tmp_path):
    path = tmp_path / "vapid_private.pem"
    keys = VapidKeys.load_or_create(path)
    assert (path.stat().st_mode & 0o777) == 0o600
    assert VapidKeys.load_or_create(path).public_key == keys.public_key
    assert len(b64url_decode(keys.public_key)) == 65

    header = keys.authorization(ENDPOINT, "mailto:jarvis@example.com")
    token = header.split("t=")[1].split(",")[0]
    assert header.endswith("k=" + keys.public_key)
    head, claims, signature = token.split(".")
    payload = json.loads(b64url_decode(claims))
    assert payload["aud"] == "https://fcm.googleapis.com"
    assert payload["sub"] == "mailto:jarvis@example.com"
    assert time.time() < payload["exp"] <= time.time() + 24 * 3600
    raw = b64url_decode(signature)
    public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),
                                                          b64url_decode(keys.public_key))
    public.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"),
                                       int.from_bytes(raw[32:], "big")),
                  f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))


@pytest.mark.parametrize("endpoint", [
    "https://fcm.googleapis.com/fcm/send/x",
    "https://updates.push.services.mozilla.com/wpush/v2/x",
    "https://web.push.apple.com/QGx",
    "https://wns2-par02p.notify.windows.com/w/?token=x",
])
def test_known_push_services_accepted(endpoint):
    check_endpoint(endpoint)


@pytest.mark.parametrize("endpoint", [
    "http://fcm.googleapis.com/fcm/send/x",       # pas https
    "https://127.0.0.1/x",                       # machine locale
    "https://evil.com/fcm.googleapis.com",
    "https://fcm.googleapis.com.evil.com/x",
    "https://192.168.1.10:3001/api/system",
    "",
])
def test_other_endpoints_refused(endpoint):
    with pytest.raises(PushError):
        check_endpoint(endpoint)


def test_store(tmp_path):
    store = PushStore(tmp_path / "push.db")
    _, p256dh, auth = browser_keys()
    store.add("owner", ENDPOINT, p256dh, auth)
    store.add("owner", ENDPOINT, p256dh, auth)  # même appareil : pas de doublon
    assert len(store.for_user("owner")) == 1 and store.for_user("alice") == []
    with pytest.raises(PushError):
        store.add("owner", ENDPOINT, "court", auth)
    with pytest.raises(PushError):
        store.add("owner", "https://evil.com/x", p256dh, auth)
    assert store.remove(ENDPOINT, "alice") is False
    assert store.remove(ENDPOINT, "owner") is True


def test_service_send(tmp_path):
    store = PushStore(tmp_path / "push.db")
    private, p256dh, auth = browser_keys()
    store.add("owner", ENDPOINT, p256dh, auth)
    store.add("owner", "https://web.push.apple.com/gone", p256dh, auth)
    store.add("owner", "https://updates.push.services.mozilla.com/broken", p256dh, auth)
    sent = []

    def post(url, body, headers):
        sent.append((url, body, headers))
        if url.endswith("gone"):
            return 410
        if url.endswith("broken"):
            raise OSError("réseau coupé")
        return 201

    service = PushService(store, VapidKeys.load_or_create(tmp_path / "v.pem"),
                          "mailto:jarvis@example.com", post=post)
    assert service.send("owner", "⏰ Rappel", "Appeler maman", tag="rappel") == 1
    url, body, headers = next(s for s in sent if s[0] == ENDPOINT)
    assert headers["Content-Encoding"] == "aes128gcm" and headers["TTL"] == "86400"
    assert headers["Authorization"].startswith("vapid t=")
    payload = json.loads(browser_decrypt(body, private, auth))
    assert payload == {"title": "⏰ Rappel", "body": "Appeler maman", "url": "/", "tag": "rappel"}
    # L'abonnement expiré (410) est supprimé, celui en erreur réseau est gardé
    assert sorted(s["endpoint"] for s in store.for_user("owner")) == [
        ENDPOINT, "https://updates.push.services.mozilla.com/broken"]
