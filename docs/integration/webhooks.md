# Compass Connect webhooks

When a user's conversation ends, Compass can send the results to your server. The notification contains the same
results as [`GET /integration/users/{external_id}/results`](README.md#get-the-results-get-integrationusersexternal_idresults),
encrypted with a secret that only your platform and Compass know.

This page builds on the [integration guide](README.md). Read it first.

## Before you start

The operator of the Compass instance turns webhooks on and allows the address of your server. Ask them to:

- turn webhooks on (`BACKEND_INTEGRATION_WEBHOOKS_ENABLED`);
- add the origin of your webhook URL to the allow-list (`BACKEND_INTEGRATION_WEBHOOK_URL_ORIGINS`), for example
  `https://api.jobs.example.org`. This list is separate from the one for the `return_url`: webhooks usually go to
  an API server, and the return URL to a web page.

While webhooks are off, a call with a `webhook_url` gets `422` and Compass creates nothing. The operator's side is in
the [getting-started guide](../getting-started/README.md#optional-integration-api).

## Ask for a notification: `webhook_url` and `webhook_secret`

Send both fields with [`POST /integration/users`](README.md#create-a-user-post-integrationusers):

| Field | Description |
|---|---|
| `webhook_url` | Where Compass sends the notifications about this user. `https` only; `http` works for `localhost` and `127.0.0.1`. Its origin must be in the instance's allow-list. Up to 2048 characters. |
| `webhook_secret` | The key that encrypts the notifications: 32 random bytes, base64url without padding (43 characters). You choose it, and Compass never returns it. |

```bash
curl -i -X POST "$BACKEND_URL/integration/users" \
  -H "x-api-key: $API_KEY" -H "content-type: application/json" \
  -d '{"external_id": "EXT-000123", "email": "user123@example.org",
       "webhook_url": "https://api.jobs.example.org/compass/webhook",
       "webhook_secret": "'"$WEBHOOK_SECRET"'"}'
```

The response echoes `user.webhook_url`. It never contains the secret.

- **Send them together.** One without the other gets `422`.
- **Each call replaces them.** A call without them removes them, and Compass no longer notifies you about this user.
  Send them on every call if you want the notifications.
- **One secret or one per user.** Compass stores the secret given in the latest call for each user. You can use one
  secret for all your users or a secret per user.
- **Keep the secret on your server**, like the API key. Whoever has it can read the notifications and forge them.

Generate a secret:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"
```

## What Compass sends

When a conversation ends, Compass sends a `POST` to the user's `webhook_url`, usually within 10 seconds:

```http
POST /compass/webhook HTTP/1.1
Host: api.jobs.example.org
Content-Type: application/jose
X-Compass-Delivery-Id: 8f2c1d7e-5b0a-4c39-9a51-2e7d0c4b6f13

eyJhbGciOiJkaXIiLCJlbmMiOiJBMjU2R0NNIn0..ZGVtby1pdi0xMjM.c2FtcGxl...LUa1nC4Hj6kVoSx3c0yU1Q
```

The body is a JWE in compact serialization ([RFC 7516](https://www.rfc-editor.org/rfc/rfc7516)), with direct
encryption: `"alg": "dir"`, `"enc": "A256GCM"`, and your `webhook_secret` (base64url-decoded) as the key. Any JOSE
library opens it. With [`jose`](https://github.com/panva/jose) in Node.js:

```javascript
import { compactDecrypt } from "jose";

const key = Buffer.from(process.env.WEBHOOK_SECRET, "base64url");
const { plaintext } = await compactDecrypt(body, key);
const notification = JSON.parse(new TextDecoder().decode(plaintext));
```

depending on your backend you will need to research how to decrypt.

**Decrypting is the check.** Decryption checks a tag that only someone with your secret can produce. When the body was made with another key, or changed on the way, decryption fails with an error and returns nothing. A body that decrypts with your secret comes from the Compass instance
## The notification

The decrypted body is JSON. The envelope is the same for every event:

```json
{
  "event": "conversation.completed",
  "version": 1,
  "delivery_id": "8f2c1d7e-5b0a-4c39-9a51-2e7d0c4b6f13",
  "sent_at": "2026-10-22T16:41:18.120000Z",
  "external_id": "EXT-000123",
  "data": {
    "session_id": 243308803207305,
    "completed_at": "2026-10-22T16:41:08.120000Z",
    "results": {
      "external_id": "EXT-000123",
      "email": "user123@example.org",
      "conversations": [ ... ]
    }
  }
}
```

| Field | Description |
|---|---|
| `event` | What happened. See [Events](#events). |
| `version` | The version of the shape of `data` for this event. |
| `delivery_id` | The id of this notification. The same in every attempt to send it. |
| `sent_at` | When this attempt was sent, UTC. |
| `external_id` | Your id for the user. |
| `data` | The content of the event. |

### Events

| `event` | When | `data` |
|---|---|---|
| `conversation.completed` | A conversation of the user ends. A new conversation of the same user later is a new notification. | `session_id`: the conversation. `completed_at`: when it ended. `results`: the same object as the [results endpoint](README.md#get-the-results-get-integrationusersexternal_idresults), as it was when this attempt was sent. |

The results in a notification can be out of date by the time you read them: the user can still edit their
experiences after the conversation ends. Call the results endpoint when you need the current state.

## Answer the notification

- **Answer with any `2xx` within 10 seconds.** Anything else counts as a failed attempt: another status, a timeout,
  a closed connection. Compass does not follow redirects.
- **Answer first, then process.** Store the body, answer `200`, and do the slow work afterwards.
- **Expect the same notification twice.** Compass can send a notification again even after you answered `2xx`, for
  example when it restarts in the middle of an attempt. Keep the `delivery_id`s you processed and ignore a repeat.
- **Check `sent_at`** if you want to refuse old notifications sent again by someone who captured one, for example
  anything older than 5 minutes. Each retry has its own `sent_at`.

## Retries

When an attempt fails, Compass tries again after 1 minute, 5 minutes, 30 minutes, 2 hours, 6 hours and 12 hours:
7 attempts over about 21 hours. Then it stops.

- Every attempt has the same `delivery_id`.
- Every attempt is built when it is sent: it goes to the `webhook_url` and uses the `webhook_secret` of the user's
  latest call, with the results as they are at that moment.
- When Compass cannot read the conversation at the time of an attempt, the attempt fails and is retried. Compass does not send incomplete results.

Compass stores the outcome of every notification. Ask the operator if one did not reach you. The results stay available from the results endpoint whether or not a notification arrived.

**For the future**

For now the only event send is when an user created via the integrations API completes a conversation in compass, in the future new events might be added and options to decide which ones you want to receive could exist. 
