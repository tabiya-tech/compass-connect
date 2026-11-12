# Monitor the channels

## Sentry tags

Every Sentry event raised while a channel works has these tags. The web app sets none of them.

| Tag | Values | Use |
|---|---|---|
| `channel` | `telegram`, `whatsapp` | Group by bot. |
| `channel_kind` | `bot` | All bot events: `channel_kind:bot`. Web app events: `!has:channel_kind`. |
| `channel_operation` | `webhook`, `initialize_conversation`, `conversation_message`, `command`, `bot_registration` | Group by what the channel was doing. `conversation_message` is a conversation turn. |
| `channel_gateway_error` | `true` | A gateway error (below). |
| `channel_slow_turn` | `true` | A slow turn (below). |

The tags of a bot turn stay on that turn. The bot runs each turn in its own Sentry isolation scope, after the webhook
has answered.

### Gateway errors

A channel turn or a call to the channel that failed: the channels service failed, Telegram did not take a reply, or
the bot could not register with Telegram at startup. Each one is a Sentry error, tagged `channel_gateway_error:true`.
Sentry groups them by channel, operation and type of error.

### Slow turns

A conversation turn of a channel user that took longer than 30 seconds (`SLOW_TURN_THRESHOLD_SECONDS` in
`backend/app/channels/config.py`). Each one is a Sentry warning, "Slow telegram turn", tagged `channel_slow_turn:true`,
with the duration in the `channel_turn` context. Sentry groups them in one issue per channel. Commands are not
measured.

## Alert rules

Create these alert rules in the Sentry project of the backend, for each environment:

| Alert | Type | Filter | Trigger |
|---|---|---|---|
| Channel gateway errors | Issue alert | `channel_gateway_error` equals `true` | A new issue, or an issue seen more than 10 times in 1 hour |
| Slow channel turns | Issue alert | `channel_slow_turn` equals `true` | The issue is seen more than 20 times in 1 hour |

Adjust the counts to the traffic of the deployment. To alert on a single bot, add a `channel` filter.

## Metrics

Every metric event has a `channel` field: `web-app`, or the bot, e.g. `telegram`. The events of a bot user's
conversation (`CONVERSATION_TURN`, `CONVERSATION_PHASE`, `EXPERIENCE_DISCOVERED`...) and their account
(`USER_ACCOUNT_CREATED`) have the channel of the bot.

The bots also record:

| Event | `event_type` | When | Fields |
|---|---|---|---|
| `BOT_USER_ACCOUNT_CREATED` | 100012 | Compass creates the anonymous user of a bot user. The account also counts in `USER_ACCOUNT_CREATED`. | `channel`, `anonymized_user_id` |
| `BOT_CONVERSATION_INITIALIZED` | 100013 | A bot user opens the bot (e.g. `/start` the first time) and gets the welcome message. | `channel`, `anonymized_user_id`, `is_new_user` |
| `BOT_INITIALIZED` | 100014 | A bot starts with a backend instance and registers with its channel. | `channel`, `registration_status`: `registered`, `unchanged` or `failed` |

`BOT_INITIALIZED` is recorded once per backend instance start. A run of `failed` means the instances cannot reach
Telegram.
