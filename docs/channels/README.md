# Compass Connect channels API

Chat bots (Telegram, WhatsApp) bring their users to a Compass Connect instance through the channels API. The bot
forwards what the user sends and posts back the messages Compass returns. The user needs no account, no password and
no invitation code: Compass creates an anonymous user for them the first time.

Compass Connect exposes the full API specification at `<BACKEND_URL>/docs` (tag "Channels") and
`<BACKEND_URL>/openapi.json`.

> Status: for now the terms are accepted for the user when the bot initializes the conversation, and every message
> gets the reply "Hello world". The real conversation comes next.

## Before you start

Ask the operator of the Compass instance for:

- **The backend URL** (`BACKEND_URL`).
- **An API key**, to send in the `x-api-key` header. The channels API does not use Firebase tokens.

Call the API from the bot's server only.

## How it works

1. The user opens the bot (e.g. `/start` on Telegram). The bot calls `POST /api/channels/conversations`. The first
   time, Compass creates an anonymous user, their preferences and a conversation session, and records the terms as
   accepted. Later calls for the same user reuse them.
2. The bot sends the returned welcome message.
3. Every time the user sends something, the bot calls `POST /api/channels/conversations/{channel_user_id}/messages`
   and sends the returned messages.

## Initialize a conversation: `POST /api/channels/conversations`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | `telegram` or `whatsapp`. |
| `channel_user_id` | yes | The id of the user on the channel, e.g. the Telegram user id. 1 to 128 characters: letters, digits and `.` `_` `:` `@` `+` `-`. One `channel` and `channel_user_id` is one Compass user. |

```bash
curl -X POST "$BACKEND_URL/api/channels/conversations" \
  -H "x-api-key: $API_KEY" -H "content-type: application/json" \
  -d '{"channel": "telegram", "channel_user_id": "100200300"}'
```

## Send a message: `POST /api/channels/conversations/{channel_user_id}/messages`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | `telegram` or `whatsapp`. |
| `channel_user_id` | yes | The same id as in the path. |
| `text` | no | The text the user typed, or the text of a choice they tapped. At most 1000 characters. |
| `command` | no | The command the user sent, e.g. `/start`, `/restart`, `/report`. |

```bash
curl -X POST "$BACKEND_URL/api/channels/conversations/100200300/messages" \
  -H "x-api-key: $API_KEY" -H "content-type: application/json" \
  -d '{"channel": "telegram", "channel_user_id": "100200300", "text": "Hi"}'
```

## Responses

Both routes return a list of messages to send to the user, in order:

```json
[{"text": "Hello world", "choices": [], "document": null}]
```

- `choices`: buttons to show where the channel supports them. When the user taps one, send its text as the `text` of
  the next message.
- `document`: a file to send, e.g. the skills report PDF (not sent yet).

| Status | When |
|---|---|
| `403` | Missing or wrong `x-api-key`. |
| `404` | The bot sends a message for a user whose conversation was never initialized. |
| `422` | Invalid body, or a `channel_user_id` in the body different from the one in the path. |

## Privacy

The `channel_user_id` is personal data. Compass stores it with the user's preferences, and keeps it out of its own
logs.
