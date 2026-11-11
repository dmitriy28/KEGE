from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


PBKDF2_ROUNDS = 310_000


def hash_secret(secret: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_secret(secret: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_b64, digest_b64 = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS, dklen=32)


def encrypt_json(value: Any, password: str) -> bytes:
    salt, nonce = os.urandom(16), os.urandom(12)
    plaintext = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(_key(password, salt)).encrypt(nonce, plaintext, b"KEGE-KEYS-V1")
    envelope = {
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-HMAC-SHA256",
        "rounds": PBKDF2_ROUNDS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    return json.dumps(envelope, ensure_ascii=False).encode("utf-8")


def decrypt_json(blob: bytes, password: str) -> Any:
    envelope = json.loads(blob.decode("utf-8"))
    if envelope.get("algorithm") != "AES-256-GCM":
        raise ValueError("Неподдерживаемый формат зашифрованных ключей")
    salt = base64.b64decode(envelope["salt"])
    nonce = base64.b64decode(envelope["nonce"])
    ciphertext = base64.b64decode(envelope["ciphertext"])
    plaintext = AESGCM(_key(password, salt)).decrypt(nonce, ciphertext, b"KEGE-KEYS-V1")
    return json.loads(plaintext.decode("utf-8"))

