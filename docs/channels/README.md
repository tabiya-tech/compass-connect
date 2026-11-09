# Compass Connect channels API

Chat bots (Telegram, WhatsApp) bring their users to a Compass Connect instance through the channels API. The bot
forwards what the user sends and posts back the messages Compass returns. The user needs no account, no password and
no invitation code: Compass creates an anonymous user for them the first time.

Compass Connect exposes the full API specification at `<BACKEND_URL>/docs` (tag "Channels") and
`<BACKEND_URL>/openapi.json`.

> Status: for now the terms are accepted for the user when the bot initializes the conversation, and `/report` does not
> send the skills report yet.
>
> TODO: translate the texts of the bot itself (help, prompts, errors): the `channels` keys of
> `backend/app/i18n/locales/*/messages.json` are in English in every language. The conversation itself comes from
> Compass in the language of the user.

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
   and sends the returned messages. The text goes to the user's Compass conversation, the same one the web app runs.
   Compass handles the messages of a user one at a time, in the order they arrive.

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

Send either `text` or `command`. When both are set, Compass handles the command.

### Commands

| Command | What Compass replies |
|---|---|
| `/start` | For a new conversation, its first message. Otherwise a "welcome back" message: the user continues where they left off. |
| `/restart` | Starts a new conversation (a new session) and replies with its first message. |
| `/report` | The skills report (for now, a message that it is not available yet). |
| `/help` | The help text with the commands. Any other command gets it too. |

Compass ignores the bot name Telegram adds in groups (`/start@CompassBot`) and the case of the command.

```bash
curl -X POST "$BACKEND_URL/api/channels/conversations/100200300/messages" \
  -H "x-api-key: $API_KEY" -H "content-type: application/json" \
  -d '{"channel": "telegram", "channel_user_id": "100200300", "text": "Hi"}'
```

## Responses

Both routes return a list of messages to send to the user, in order:

```json
[{"text": "Hi! I'm Compass. ...", "choices": ["Let's start", "How long does it take?"], "document": null}]
```

- `choices`: buttons to show where the channel supports them. When the user taps one, send its text as the `text` of
  the next message.
- `document`: a file to send, e.g. the skills report PDF (not sent yet).
- When the conversation ends, the last message tells the user they can send `/report` or `/restart`.

### Preference questions (best-worst tasks)

During preference elicitation Compass shows groups of options, lettered A, B, C... and asks which one the user likes
most and which one least. On a channel this takes two messages:

1. Compass sends the options with the question "Which one would you like the *most*?" and the letters as `choices`.
2. The user replies with a letter (e.g. `B`). Compass asks "And which one would you like the *least*?", with the
   other letters as `choices`.
3. The user replies with another letter, and Compass continues the conversation.

A letter that is not an option is asked again. The user can also answer in their own words, e.g.
"Most: B, Least: D".

### Errors in the conversation

When the conversation cannot continue, the response is still `200` with a message for the user, e.g. when the
conversation has already ended ("send /restart to start a new one"), or when something went wrong on the Compass side
("please try again").

| Status | When |
|---|---|
| `403` | Missing or wrong `x-api-key`. |
| `404` | The bot sends a message for a user whose conversation was never initialized. |
| `422` | Invalid body, or a `channel_user_id` in the body different from the one in the path. |

## Privacy

The `channel_user_id` is personal data. Compass stores it with the user's preferences, and keeps it out of its own
logs.
