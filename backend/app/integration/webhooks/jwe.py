"""
The body of a webhook notification: a JWE in compact serialization (RFC 7516) with direct encryption, `alg` "dir" and
`enc` "A256GCM", the key being the platform's webhook secret. AES-GCM authenticates as it encrypts: only someone with
the secret can produce a body that decrypts, so it also proves the notification comes from this Compass instance.
Any JOSE library opens it, e.g. `compactDecrypt(body, key)` of the Node `jose` package.
"""

import base64
import json
import os
from typing import Any, Mapping

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, SecretStr

_PROTECTED_HEADER = {"alg": "dir", "enc": "A256GCM"}
_KEY_LENGTH = 32
_IV_LENGTH = 12
"""
96 bits, the IV length JWA (RFC 7518) requires for AES-GCM. A new random IV for every body: with GCM, the same key and
IV twice would reveal both plaintexts.
"""
_TAG_LENGTH = 16


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def encrypt_webhook_payload(payload: BaseModel, secret: SecretStr) -> str:
    """
    :param payload: the notification, serialized as JSON
    :param secret: the platform's webhook secret, 32 bytes base64url-encoded
    :return: the compact JWE, the body of the notification
    :raises ValueError: if the secret is not 32 bytes
    """
    key = b64url_decode(secret.get_secret_value())
    if len(key) != _KEY_LENGTH:
        raise ValueError("The webhook secret must be 32 bytes.")
    return _encrypt_compact(payload.model_dump_json().encode("utf-8"), key, _PROTECTED_HEADER, os.urandom(_IV_LENGTH))


def _encrypt_compact(plaintext: bytes, key: bytes, header: Mapping[str, Any], iv: bytes) -> str:
    """
    The content encryption of RFC 7516 (5.1) with AES-GCM. With "dir" there is no encrypted key: its part is empty.
    """
    protected = b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    # the additional authenticated data is the encoded protected header, so the header cannot be changed either
    sealed = AESGCM(key).encrypt(iv, plaintext, protected.encode("ascii"))
    ciphertext, tag = sealed[:-_TAG_LENGTH], sealed[-_TAG_LENGTH:]
    return ".".join([protected, "", b64url_encode(iv), b64url_encode(ciphertext), b64url_encode(tag)])
