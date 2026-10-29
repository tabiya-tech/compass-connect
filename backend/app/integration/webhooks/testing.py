"""
For the tests: what a platform does to open a notification. Written from RFC 7516 (5.2), not from jwe.py, so the tests
do not only check that the code agrees with itself.
"""

import base64
import json

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def decrypt(body: str, secret: str) -> tuple[dict, bytes]:
    """
    :param body: the compact JWE
    :param secret: the platform's webhook secret, base64url
    :return: the protected header and the plaintext
    :raises cryptography.exceptions.InvalidTag: if the secret is wrong or anything in the body was changed
    """
    protected, encrypted_key, iv, ciphertext, tag = body.split(".")
    if encrypted_key != "":
        raise ValueError('"dir" has no encrypted key')
    sealed = b64url_decode(ciphertext) + b64url_decode(tag)
    plaintext = AESGCM(b64url_decode(secret)).decrypt(b64url_decode(iv), sealed, protected.encode("ascii"))
    return json.loads(b64url_decode(protected)), plaintext
