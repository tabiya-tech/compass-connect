import secrets

import pytest
from cryptography.exceptions import InvalidTag
from pydantic import BaseModel, SecretStr

from app.integration.webhooks.jwe import encrypt_webhook_payload, _encrypt_compact
from app.integration.webhooks.testing import decrypt, b64url_decode, b64url_encode


class _Payload(BaseModel):
    event: str
    external_id: str
    note: str


_PAYLOAD = _Payload(event="conversation.completed", external_id="ext-1", note="Atención al público, 3 años")


def _new_secret() -> str:
    return secrets.token_urlsafe(32)


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
    given_secret = _new_secret()

    # WHEN a payload is encrypted with it
    actual = encrypt_webhook_payload(_PAYLOAD, SecretStr(given_secret))

    # THEN the platform decrypts it with the same secret, and gets the payload as JSON
    actual_header, actual_plaintext = decrypt(actual, given_secret)
    assert actual_header == {"alg": "dir", "enc": "A256GCM"}
    assert _Payload.model_validate_json(actual_plaintext) == _PAYLOAD
    # AND nothing of the payload can be read in the body
    assert "ext-1" not in actual
    assert "conversation" not in actual


def test_the_same_payload_encrypts_differently_every_time():
    # a new random IV each time: with AES-GCM, the same key and IV twice would reveal both payloads
    given_secret = SecretStr(_new_secret())
    actual_first = encrypt_webhook_payload(_PAYLOAD, given_secret)
    actual_second = encrypt_webhook_payload(_PAYLOAD, given_secret)
    assert actual_first != actual_second


def test_another_secret_cannot_open_it():
    # this is also what proves the origin: a body made without the platform's secret does not decrypt
    actual = encrypt_webhook_payload(_PAYLOAD, SecretStr(_new_secret()))
    with pytest.raises(InvalidTag):
        decrypt(actual, _new_secret())


@pytest.mark.parametrize("given_part", [0, 2, 3, 4], ids=["protected header", "iv", "ciphertext", "tag"])
def test_any_change_to_the_body_is_detected(given_part: int):
    # GIVEN a body
    given_secret = _new_secret()
    parts = encrypt_webhook_payload(_PAYLOAD, SecretStr(given_secret)).split(".")

    # WHEN one bit of one of its parts is changed
    changed = bytearray(b64url_decode(parts[given_part]))
    changed[0] ^= 1
    parts[given_part] = b64url_encode(bytes(changed))

    # THEN it does not decrypt
    with pytest.raises(InvalidTag):
        decrypt(".".join(parts), given_secret)


@pytest.mark.parametrize("given_secret", [
    "s" * 42,
    secrets.token_urlsafe(16),
    secrets.token_urlsafe(48),
], ids=["shorter", "16 bytes", "48 bytes"])
def test_the_secret_must_be_32_bytes(given_secret: str):
    # the request is validated, but a stored secret is checked again: AES-GCM would also accept 16 or 24 bytes
    with pytest.raises(ValueError):
        encrypt_webhook_payload(_PAYLOAD, SecretStr(given_secret))
