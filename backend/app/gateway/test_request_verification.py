import base64
import hashlib
import hmac
import json
import time
from http import HTTPStatus
from typing import Any, Optional

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import app.gateway.firebase_tokens as firebase_tokens_module
from app.gateway.firebase_tokens import _FIREBASE_ISSUER_PREFIX
from app.users.auth import Authentication, ApiKeyAuth, UserInfo

_PROJECT_ID = "test-project"
_KEY_ID = "test-key-id"

_SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY_PEM = _SIGNING_KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def _claims(**overrides: Any) -> dict:
    now = int(time.time())
    claims = {
        "iss": _FIREBASE_ISSUER_PREFIX + _PROJECT_ID,
        "aud": _PROJECT_ID,
        "sub": "user-1",
        "iat": now - 10,
        "exp": now + 3600,
        "name": "Test User",
        "email": "test@example.com",
        "firebase": {"sign_in_provider": "password"},
    }
    claims.update(overrides)
    return {key: value for key, value in claims.items() if value is not None}


def _token(claims: Optional[dict] = None, key=_SIGNING_KEY, algorithm: str = "RS256", kid: Optional[str] = _KEY_ID) -> str:
    headers = {"kid": kid} if kid else {}
    return jwt.encode(claims if claims is not None else _claims(), key, algorithm=algorithm, headers=headers)


def _hs256_token_signed_with(secret: bytes) -> str:
    """ An algorithm confusion attack token: HS256, with the (public) RSA key as the HMAC secret. PyJWT refuses to build it. """
    def _b64(data: bytes) -> bytes:
        return base64.urlsafe_b64encode(data).rstrip(b"=")

    signing_input = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": _KEY_ID}).encode()) + b"." + _b64(json.dumps(_claims()).encode())
    return (signing_input + b"." + _b64(hmac.new(secret, signing_input, hashlib.sha256).digest())).decode()


def _build_client() -> TestClient:
    app = FastAPI()
    authentication = Authentication()

    @app.get("/me")
    def _me(user_info: UserInfo = Depends(authentication.get_user_info())):
        return user_info.model_dump(mode="json", exclude={"token"})

    @app.get("/keyed", dependencies=[Depends(ApiKeyAuth())])
    def _keyed():
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="function")
def direct_ingress_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INGRESS_MODE", "direct")
    monkeypatch.setenv("TARGET_ENVIRONMENT_TYPE", "prod")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", _PROJECT_ID)
    monkeypatch.delenv("API_KEYS", raising=False)
    # Google's keys are replaced by our own test key, so we can sign tokens.

    def _get_key(key_id: str):
        if key_id != _KEY_ID:
            raise jwt.InvalidTokenError("Unknown signing key id")
        return _SIGNING_KEY.public_key()

    monkeypatch.setattr(firebase_tokens_module._firebase_public_keys, "get_key", _get_key)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestDirectIngressFirebaseTokenVerification:
    def test_valid_token(self, direct_ingress_env):
        # GIVEN a token properly signed, for the right project
        given_token = _token()

        # WHEN calling an authenticated endpoint
        response = _build_client().get("/me", headers=_bearer(given_token))

        # THEN the user is authenticated with the info from the verified claims
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"user_id": "user-1", "name": "Test User", "email": "test@example.com",
                                   "sign_in_provider": "password", "role": None, "institution_id": None}

    def test_role_and_institution_claims(self, direct_ingress_env):
        # GIVEN a valid token with the custom claims
        given_token = _token(_claims(role="institution_staff", institutionId="inst-1"))

        # WHEN calling an authenticated endpoint
        response = _build_client().get("/me", headers=_bearer(given_token))

        # THEN the custom claims are available in the user info
        assert response.status_code == HTTPStatus.OK
        assert response.json()["role"] == "institution_staff"
        assert response.json()["institution_id"] == "inst-1"

    @pytest.mark.parametrize("given_sign_in_provider", ["password", "google.com", "anonymous", "custom"])
    def test_sign_in_providers(self, direct_ingress_env, given_sign_in_provider: str):
        # GIVEN a valid token from a supported sign-in provider ("custom" is the hand-off link login)
        given_token = _token(_claims(firebase={"sign_in_provider": given_sign_in_provider}))

        # WHEN calling an authenticated endpoint
        response = _build_client().get("/me", headers=_bearer(given_token))

        # THEN the user is authenticated with that sign-in provider
        assert response.status_code == HTTPStatus.OK
        assert response.json()["sign_in_provider"] == given_sign_in_provider

    @pytest.mark.parametrize("given_token", [
        pytest.param(_token(_claims(firebase={"sign_in_provider": "phone"})), id="unsupported sign-in provider"),
        pytest.param(_token(key=_OTHER_SIGNING_KEY), id="forged signature"),
        pytest.param(_token(_claims(exp=int(time.time()) - 3600)), id="expired"),
        pytest.param(_token(_claims(iat=int(time.time()) + 3600)), id="issued in the future"),
        pytest.param(_token(_claims(aud="another-project")), id="wrong audience"),
        pytest.param(_token(_claims(iss="https://securetoken.google.com/another-project")), id="wrong issuer"),
        pytest.param(_token(_claims(sub=None)), id="missing subject"),
        pytest.param(_token(_claims(sub="")), id="empty subject"),
        pytest.param(_token(_claims(exp=None)), id="missing expiry"),
        pytest.param(_token(kid="another-key-id"), id="unknown key id"),
        pytest.param(_token(kid=None), id="missing key id"),
        pytest.param("not-a-jwt", id="not a jwt"),
        pytest.param(jwt.encode(_claims(), key=None, algorithm="none", headers={"kid": _KEY_ID}), id="unsigned (alg none)"),
        pytest.param(_hs256_token_signed_with(_PUBLIC_KEY_PEM),
                     id="HS256 signed with the RSA public key as secret"),
    ])
    def test_invalid_token_is_rejected(self, direct_ingress_env, given_token: str):
        # GIVEN an invalid token
        # WHEN calling an authenticated endpoint
        response = _build_client().get("/me", headers=_bearer(given_token))

        # THEN the request is unauthorized
        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_small_clock_skew_is_tolerated(self, direct_ingress_env):
        # GIVEN a token issued a few seconds "in the future" because the clock of the host is slightly behind
        given_token = _token(_claims(iat=int(time.time()) + 5))

        # WHEN calling an authenticated endpoint
        response = _build_client().get("/me", headers=_bearer(given_token))

        # THEN the token is accepted
        assert response.status_code == HTTPStatus.OK

    def test_missing_authorization_header(self, direct_ingress_env):
        # WHEN calling an authenticated endpoint without credentials
        response = _build_client().get("/me")

        # THEN the request is rejected
        assert response.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN)

    def test_api_gateway_header_is_ignored(self, direct_ingress_env):
        # GIVEN a forged api gateway header and an invalid token
        forged_info = base64.b64encode(json.dumps({"sub": "admin", "firebase": {"sign_in_provider": "password"}}).encode()).decode()

        # WHEN calling an authenticated endpoint
        response = _build_client().get("/me", headers={**_bearer("not-a-jwt"), "x-apigateway-api-userinfo": forged_info})

        # THEN the forged header does not authenticate the user
        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_missing_project_id_rejects(self, direct_ingress_env, monkeypatch: pytest.MonkeyPatch):
        # GIVEN no FIREBASE_PROJECT_ID is configured
        monkeypatch.delenv("FIREBASE_PROJECT_ID")

        # WHEN calling with an otherwise valid token
        response = _build_client().get("/me", headers=_bearer(_token()))

        # THEN the request is unauthorized, never accepted
        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_local_environment_is_verified_too(self, direct_ingress_env, monkeypatch: pytest.MonkeyPatch):
        # GIVEN the local environment
        monkeypatch.setenv("TARGET_ENVIRONMENT_TYPE", "local")

        # WHEN calling an authenticated endpoint with a forged token, then with a valid one
        forged_response = _build_client().get("/me", headers=_bearer(_token(key=_OTHER_SIGNING_KEY)))
        valid_response = _build_client().get("/me", headers=_bearer(_token()))

        # THEN the tokens are still verified: the forged one is unauthorized, the valid one is accepted
        assert forged_response.status_code == HTTPStatus.UNAUTHORIZED
        assert valid_response.status_code == HTTPStatus.OK


class TestGatewayIngress:
    """Behind the API Gateway (the default ingress mode) the backend trusts the gateway, as before the direct mode existed."""

    @pytest.fixture(autouse=True)
    def _gateway_ingress(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("INGRESS_MODE", raising=False)

    def test_local_decodes_without_verifying(self, monkeypatch: pytest.MonkeyPatch):
        # GIVEN the local environment and a token signed with an unknown key
        monkeypatch.setenv("TARGET_ENVIRONMENT_TYPE", "local")

        # WHEN calling an authenticated endpoint
        response = _build_client().get("/me", headers=_bearer(_token(key=_OTHER_SIGNING_KEY)))

        # THEN the token is accepted unverified, as before
        assert response.status_code == HTTPStatus.OK
        assert response.json()["user_id"] == "user-1"

    @pytest.mark.parametrize("environment", ["dev", "prod", "anything-else"])
    def test_other_environments_use_the_api_gateway_header(self, monkeypatch: pytest.MonkeyPatch, environment: str):
        # GIVEN a deployed (gateway) environment
        monkeypatch.setenv("TARGET_ENVIRONMENT_TYPE", environment)
        gateway_info = base64.b64encode(json.dumps(_claims()).encode()).decode().rstrip("=")

        # WHEN the gateway header is present, any token value
        response = _build_client().get("/me", headers={**_bearer("whatever"), "x-apigateway-api-userinfo": gateway_info})

        # THEN the user comes from the header
        assert response.status_code == HTTPStatus.OK
        assert response.json()["user_id"] == "user-1"

        # AND without the header the request is unauthorized
        assert _build_client().get("/me", headers=_bearer(_token())).status_code == HTTPStatus.UNAUTHORIZED

    def test_custom_token_session_is_accepted(self, monkeypatch: pytest.MonkeyPatch):
        # GIVEN a deployed environment and the gateway header of a session started with a custom token (hand-off link)
        monkeypatch.setenv("TARGET_ENVIRONMENT_TYPE", "prod")
        gateway_info = base64.b64encode(json.dumps(_claims(firebase={"sign_in_provider": "custom"})).encode()).decode().rstrip("=")

        # WHEN calling an authenticated endpoint
        response = _build_client().get("/me", headers={**_bearer("whatever"), "x-apigateway-api-userinfo": gateway_info})

        # THEN the user is authenticated with the custom sign-in provider
        assert response.status_code == HTTPStatus.OK
        assert response.json()["sign_in_provider"] == "custom"

    @pytest.mark.parametrize("given_ingress_mode", ["gateway", " GATEWAY ", ""])
    def test_gateway_mode_set_explicitly(self, monkeypatch: pytest.MonkeyPatch, given_ingress_mode: str):
        # GIVEN the gateway ingress mode set explicitly (in any case) or left empty, in a deployed environment
        monkeypatch.setenv("INGRESS_MODE", given_ingress_mode)
        monkeypatch.setenv("TARGET_ENVIRONMENT_TYPE", "prod")
        gateway_info = base64.b64encode(json.dumps(_claims()).encode()).decode()

        # WHEN the gateway header is present
        response = _build_client().get("/me", headers={**_bearer("whatever"), "x-apigateway-api-userinfo": gateway_info})

        # THEN the user comes from the header
        assert response.status_code == HTTPStatus.OK
        assert response.json()["user_id"] == "user-1"

    @pytest.mark.parametrize("environment", ["local", "dev", "prod"])
    def test_api_key_is_not_validated_by_the_backend(self, monkeypatch: pytest.MonkeyPatch, environment: str):
        # GIVEN an environment where the api gateway validates the keys, and no API_KEYS configured
        monkeypatch.setenv("TARGET_ENVIRONMENT_TYPE", environment)
        monkeypatch.delenv("API_KEYS", raising=False)

        # WHEN any key is sent
        response = _build_client().get("/keyed", headers={"x-api-key": "some-key"})

        # THEN it is accepted by the app (the gateway is the one validating), as before
        assert response.status_code == HTTPStatus.OK


class TestDirectIngressApiKeys:
    def test_valid_key(self, direct_ingress_env, monkeypatch: pytest.MonkeyPatch):
        # GIVEN two configured keys
        monkeypatch.setenv("API_KEYS", "key-one, key-two")

        # WHEN calling with the second key
        response = _build_client().get("/keyed", headers={"x-api-key": "key-two"})

        # THEN it is accepted
        assert response.status_code == HTTPStatus.OK

    def test_wrong_key(self, direct_ingress_env, monkeypatch: pytest.MonkeyPatch):
        # GIVEN configured keys
        monkeypatch.setenv("API_KEYS", "key-one,key-two")

        # WHEN calling with another key
        response = _build_client().get("/keyed", headers={"x-api-key": "key-three"})

        # THEN it is forbidden
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_missing_key(self, direct_ingress_env, monkeypatch: pytest.MonkeyPatch):
        # GIVEN configured keys
        monkeypatch.setenv("API_KEYS", "key-one")

        # WHEN calling without the header
        response = _build_client().get("/keyed")

        # THEN it is rejected
        assert response.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN)

    @pytest.mark.parametrize("given_api_keys", [None, "", " , "])
    def test_no_keys_configured_disables_the_endpoints(self, direct_ingress_env, monkeypatch: pytest.MonkeyPatch, given_api_keys: Optional[str]):
        # GIVEN no usable API_KEYS
        if given_api_keys is not None:
            monkeypatch.setenv("API_KEYS", given_api_keys)

        # WHEN calling with any key, including an empty one
        # THEN it is forbidden
        assert _build_client().get("/keyed", headers={"x-api-key": "anything"}).status_code == HTTPStatus.FORBIDDEN
        assert _build_client().get("/keyed", headers={"x-api-key": ""}).status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN)
