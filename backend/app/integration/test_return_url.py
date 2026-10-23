import pytest

from app.integration.return_url import InvalidReturnUrlError, validate_return_url

_ALLOWED = ["https://Partner.Example.org/", "http://localhost:3000"]


@pytest.mark.parametrize("given_url", [
    "https://partner.example.org/perfil?vuelta=1#a",
    "HTTPS://PARTNER.example.org",
    "http://localhost:3000/return",
])
def test_allowed(given_url: str):
    validate_return_url(given_url, _ALLOWED)


@pytest.mark.parametrize("given_url, given_allowed", [
    pytest.param("https://other.example.org/", _ALLOWED, id="other origin"),
    pytest.param("https://partner.example.org.other.example.org/", _ALLOWED, id="allowed origin as a prefix"),
    pytest.param("https://partner.example.org:8443/", _ALLOWED, id="other port"),
    pytest.param("https://partner.example.org@other.example.org/", _ALLOWED, id="credentials"),
    pytest.param("http://partner.example.org/", ["http://partner.example.org"], id="http not on localhost"),
    pytest.param("//partner.example.org/", _ALLOWED, id="scheme-relative"),
    pytest.param("javascript:alert(1)", _ALLOWED, id="javascript"),
    pytest.param("https://partner.example.org:99999/", _ALLOWED, id="bad port"),
    pytest.param("https://partner.example.org/", [], id="empty allow-list"),
])
def test_refused(given_url: str, given_allowed: list[str]):
    with pytest.raises(InvalidReturnUrlError) as e:
        validate_return_url(given_url, given_allowed)
    assert str(e.value)
