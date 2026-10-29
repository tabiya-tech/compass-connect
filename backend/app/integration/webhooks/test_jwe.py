import base64
import json
import secrets

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, SecretStr

from app.integration.webhooks.jwe import encrypt_webhook_payload, _encrypt_compact


class _Payload(BaseModel):
    event: str
    external_id: str
    note: str


_GIVEN_PAYLOAD = _Payload(event="conversation.completed", external_id="ext-1", note="Atención al público, 3 años")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _decrypt(jwe: str, key: bytes) -> tuple[dict, bytes]:
    """
    What a platform does to open the body, written from RFC 7516 (5.2), independently of the code under test.

    :return: the protected header and the plaintext
    :raises InvalidTag: if the key is wrong or anything was changed
    """
    protected, encrypted_key, iv, ciphertext, tag = jwe.split(".")
    assert encrypted_key == ""  # "dir": no encrypted key
    plaintext = AESGCM(key).decrypt(_b64url_decode(iv), _b64url_decode(ciphertext) + _b64url_decode(tag),
                                    protected.encode("ascii"))
    return json.loads(_b64url_decode(protected)), plaintext


def _secret() -> tuple[SecretStr, bytes]:
    value = secrets.token_urlsafe(32)
    return SecretStr(value), _b64url_decode(value)


def test_known_answer_of_rfc_7516():
    # GIVEN the example of RFC 7516 appendix A.1, whose content encryption is AES-256-GCM like ours (it wraps its
    # content key with RSA, which "dir" does not: the key is used as it is)
    given_key = bytes([177, 161, 244, 128, 84, 143, 225, 115, 63, 180, 3, 255, 107, 154, 212, 246, 138, 7, 110, 91,
                       112, 46, 34, 105, 47, 130, 203, 46, 122, 234, 64, 252])
    given_iv = bytes([227, 197, 117, 252, 2, 219, 233, 68, 180, 225, 77, 219])
    given_plaintext = b"The true sign of intelligence is not knowledge but imagination."

    # WHEN it is encrypted with the same header and IV
    actual = _encrypt_compact(given_plaintext, given_key, {"alg": "RSA-OAEP", "enc": "A256GCM"}, given_iv)

    # THEN the header, IV, ciphertext and tag are the ones of the RFC
    protected, _, iv, ciphertext, tag = actual.split(".")
    assert protected == "eyJhbGciOiJSU0EtT0FFUCIsImVuYyI6IkEyNTZHQ00ifQ"
    assert iv == "48V1_ALb6US04U3b"
    assert ciphertext == "5eym8TW_c8SuK0ltJ3rpYIzOeDQz7TALvtu6UG9oMo4vpzs9tX_EFShS8iB7j6jiSdiwkIr3ajwQzaBtQD_A"
    assert tag == "XFBoMYUZodetZdvTiFvSkQ"


def test_the_platform_opens_it_with_its_secret():
    # GIVEN a platform's secret
    given_secret, given_key = _secret()

    # WHEN a payload is encrypted
    actual = encrypt_webhook_payload(_GIVEN_PAYLOAD, given_secret)

    # THEN it is a compact JWE with direct AES-256-GCM encryption, and decrypting it gives the payload as JSON
    actual_header, actual_plaintext = _decrypt(actual, given_key)
    assert actual_header == {"alg": "dir", "enc": "A256GCM"}
    assert _Payload.model_validate_json(actual_plaintext) == _GIVEN_PAYLOAD
    # AND nothing of the payload is readable in the body
    assert "ext-1" not in actual and "conversation" not in actual


def test_every_body_has_a_new_iv():
    given_secret, _ = _secret()
    actual_first = encrypt_webhook_payload(_GIVEN_PAYLOAD, given_secret)
    actual_second = encrypt_webhook_payload(_GIVEN_PAYLOAD, given_secret)
    assert actual_first.split(".")[2] != actual_second.split(".")[2]
    assert actual_first != actual_second


def test_another_secret_cannot_open_it():
    # a notification made with another key (e.g. by someone who is not this Compass instance) does not decrypt
    given_secret, _ = _secret()
    actual = encrypt_webhook_payload(_GIVEN_PAYLOAD, given_secret)
    with pytest.raises(InvalidTag):
        _decrypt(actual, _secret()[1])


@pytest.mark.parametrize("given_part", [
    pytest.param(0, id="protected header"),
    pytest.param(2, id="iv"),
    pytest.param(3, id="ciphertext"),
    pytest.param(4, id="tag"),
])
def test_any_change_is_detected(given_part: int):
    # GIVEN a body
    given_secret, given_key = _secret()
    parts = encrypt_webhook_payload(_GIVEN_PAYLOAD, given_secret).split(".")

    # WHEN one byte of one of its parts is changed
    changed = bytearray(_b64url_decode(parts[given_part]))
    changed[0] ^= 1
    parts[given_part] = base64.urlsafe_b64encode(bytes(changed)).rstrip(b"=").decode("ascii")

    # THEN it does not decrypt
    with pytest.raises(InvalidTag):
        _decrypt(".".join(parts), given_key)


@pytest.mark.parametrize("given_secret", [
    pytest.param("s" * 42, id="shorter"),
    pytest.param(secrets.token_urlsafe(16), id="16 bytes"),
    pytest.param(secrets.token_urlsafe(48), id="48 bytes"),
])
def test_secret_must_be_32_bytes(given_secret: str):
    # the request is validated, but a stored secret is checked again: AESGCM would accept a 16 or 24 bytes key
    with pytest.raises(ValueError):
        encrypt_webhook_payload(_GIVEN_PAYLOAD, SecretStr(given_secret))
