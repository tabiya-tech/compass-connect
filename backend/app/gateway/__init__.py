"""
Everything that depends on how the requests reach the backend, set with the INGRESS_MODE env variable:

- `gateway` (default, used by the cloud deployments): the Google API Gateway is in front of the backend.
  It verifies the Firebase ID tokens and sends their claims in the `x-apigateway-api-userinfo` header,
  validates the `x-api-key` keys and applies the rate limit. The backend trusts it.
  With TARGET_ENVIRONMENT_TYPE=local there is no gateway: the tokens are decoded without being verified (only on your own machine).
- `direct`: nothing is in front of the backend (any cloud provider or on-premise). The backend does the work of the gateway:
  it verifies the Firebase ID tokens of FIREBASE_PROJECT_ID, accepts only the API_KEYS keys and limits the requests per client IP
  (BACKEND_RATE_LIMIT_PER_MINUTE).

- ingress_mode.py: the mode and its configuration, validated at start-up.
- request_verification.py: verifies the tokens and the API keys according to the mode, used by app.users.auth.
- google_api_gateway.py: reads the claims sent by the Google API Gateway.
- firebase_tokens.py, api_keys.py, rate_limiter.py: what the backend does itself in the direct mode.
"""
