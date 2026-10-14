import hmac
import os


def is_configured_api_key(api_key: str) -> bool:
    """
    :param api_key: The key sent in the `x-api-key` header.
    :return: True if the key is one of the keys configured in API_KEYS (comma separated).
             False for any key when none are configured.
    """
    valid_keys = [key.strip() for key in os.getenv("API_KEYS", "").split(",") if key.strip()]
    # Compare against all the keys (no early exit) in constant time.
    matches = [hmac.compare_digest(api_key.encode(), valid_key.encode()) for valid_key in valid_keys]
    return any(matches)
