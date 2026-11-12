# Deploy the channels

The channels are off by default. A deployment turns them on with two environment variables:

| Variable | Default | Description |
|---|---|---|
| `BACKEND_ENABLE_CHANNELS` | `false` | `true` registers the `/api/channels/**` routes: the channels API, and the webhooks of the bots that are enabled. |
| `BACKEND_ENABLE_TELEGRAM_BOT` | `false` | `true` runs the Telegram bot. Needs `BACKEND_ENABLE_CHANNELS=true`. |

When `BACKEND_ENABLE_CHANNELS` is not `true`, the backend registers none of the `/api/channels/**` routes. The routes
are then missing from `/openapi.json` and from the API gateway, which is built from it, and every call to them gets
`404`. With `BACKEND_ENABLE_CHANNELS=true` alone, the channels API is up for bots that run elsewhere, and no bot runs
in the backend.

The backend does not start when `BACKEND_ENABLE_TELEGRAM_BOT=true` and `BACKEND_ENABLE_CHANNELS` is not `true`, or
when the Telegram bot is enabled without its settings below.

## Telegram settings

| Variable | Description |
|---|---|
| `BACKEND_TELEGRAM_BOT_TOKEN` | Required when the bot is enabled. The token of the bot, from @BotFather. A secret. |
| `BACKEND_TELEGRAM_WEBHOOK_SECRET` | Required when the bot is enabled. 1 to 256 characters: letters, digits, `_` and `-`, e.g. `openssl rand -hex 32`. Telegram sends it with every update. A secret. |
| `BACKEND_TELEGRAM_WEBHOOK_URL` | Optional. The public HTTPS URL of the webhook. Default: `<BACKEND_URL>/api/channels/telegram/webhook`. Locally, the URL of an HTTPS tunnel to the backend. |

## Telegram runs on a webhook only

The Telegram bot receives its updates on a webhook, `POST /api/channels/telegram/webhook`. It never polls Telegram
with `getUpdates`, and there is no setting to make it poll.

Telegram delivers the updates of a bot to one place only: one webhook URL, or one `getUpdates` poller. With polling,
every backend instance would poll the same token. Telegram answers all but one of them with a `409 Conflict`, and
the updates go to whichever instance polled last. With a webhook, Telegram posts each update once to the URL, and the
load balancer gives it to one instance. Cloud Run can scale the backend to any number of instances. The backend also
records each update id (`channel_received_updates`, kept a day) and skips an update it already received, for the
times Telegram sends one again.

At startup, each instance checks the webhook registered with Telegram, and registers its own when it differs. Setting
a webhook also stops any `getUpdates` polling of the token.

### One deployment per bot token

The webhook belongs to the token. Two deployments that run with the same token (two environments, or a laptop and a
server) take the webhook from each other at every startup. Only the last one to start gets the updates, and the users
of the other one get no replies. The backend logs a warning when it replaces the webhook of another URL.

- Create one bot with @BotFather for each environment (dev, test, prod), and give each environment its own token.
- Locally, use a bot of your own. Never run a local backend with the token of a deployed bot.
- To move a bot to another deployment, set `BACKEND_ENABLE_TELEGRAM_BOT=false` on the old deployment first, then enable it on the new one.
  Disabling the bot does not remove the webhook from Telegram: until the new deployment starts, Telegram keeps
  posting to the old URL, which answers `404`.

To see where Telegram sends the updates of a bot:

```bash
curl "https://api.telegram.org/bot$BACKEND_TELEGRAM_BOT_TOKEN/getWebhookInfo"
```

`url` is the registered webhook (it ends with `?v=` and a hash of the secret), and `last_error_message` is the last
error Telegram got from it.

## Run locally

1. Create a bot with @BotFather, and copy its token.
2. Start a tunnel to the backend, e.g. `cloudflared tunnel --url http://localhost:8080`.
3. Set in `backend/.env`:

   ```bash
   BACKEND_ENABLE_CHANNELS=true
   BACKEND_ENABLE_TELEGRAM_BOT=true
   BACKEND_TELEGRAM_BOT_TOKEN=<token>
   BACKEND_TELEGRAM_WEBHOOK_SECRET=<openssl rand -hex 32>
   BACKEND_TELEGRAM_WEBHOOK_URL=https://<tunnel>/api/channels/telegram/webhook
   ```

4. Start the backend. It registers the webhook and the command menu, then the bot answers on Telegram.

## Deploy

The backend IaC passes `BACKEND_ENABLE_CHANNELS`, `BACKEND_ENABLE_TELEGRAM_BOT` and the `BACKEND_TELEGRAM_*` variables
to Cloud Run. Set them in the environment of the deployment (see `iac/templates/env.template`), and redeploy the
backend. The API gateway config is rebuilt from the backend's `/openapi.json`, so it gets the channels routes when
they are enabled, and loses them when they are disabled.
