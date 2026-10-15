import base64
import json

from fastapi import Request, HTTPException, status

USER_INFO_HEADER = "x-apigateway-api-userinfo"
"""
The header in which the Google API Gateway sends the claims of the Firebase ID token it verified.
"""


def decode_user_info_header(request: Request) -> dict:
    """
    Returns the claims the Google API Gateway verified and sent, Base64-encoded, in the `x-apigateway-api-userinfo` header.
    If the header is missing, the user should be treated as unauthenticated.
    While this scenario should not occur under normal circumstances, since the API Gateway is expected to always
    include the header, we implement this check as a precautionary measure. For example, such an issue could arise
    if the API Gateway is improperly configured or if the incoming request does not originate from the API Gateway.
    :param request: The request.
    :return: The claims of the token.
    :raises HTTPException: 401 if the header is missing.
    :raises ValueError: if the header is not valid base64 or JSON.
    """
    auth_info_b64 = request.headers.get(USER_INFO_HEADER)
    if not auth_info_b64:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="forbidden")

    # The user info is encoded as base 64 string by the api-gateway
    return _decode_user_info_api_gateway(auth_info_b64)


def _decode_user_info_api_gateway(auth_info_b64):
    """
    Decodes a base64-encoded string containing user information and returns it as a dictionary.
    The api-gateway does not allways send the correct padding, so this function
    handles partial padding (missing one or two `=` characters). Rejects invalid input.

    Args:
        auth_info_b64 (str): The base64-encoded string containing JSON user data.

    Returns:
        dict: Decoded user information as a Python dictionary.

    Raises:
        ValueError: If the input is not valid base64 or if the JSON is invalid.
    """
    try:
        # Check if padding is needed and apply it
        padding_needed = len(auth_info_b64) % 4
        if padding_needed == 1:
            raise ValueError("Invalid base64 input: length is not compatible with base64 encoding")
        elif padding_needed == 2:
            padded_base64 = auth_info_b64 + '=='  # Add two `=` characters
        elif padding_needed == 3:
            padded_base64 = auth_info_b64 + '='  # Add one `=` character
        else:
            padded_base64 = auth_info_b64  # No padding needed

        # Decode the base64 string
        decoded_bytes = base64.b64decode(padded_base64.encode('utf-8'))

        # Convert bytes to string
        decoded_string = decoded_bytes.decode('utf-8')

        # Parse JSON from the decoded string
        user_info = json.loads(decoded_string)

        return user_info

    except Exception as e:
        raise ValueError("Invalid base64 or JSON input") from e
