# Compass Connect integration API

Another platform (a job portal, a training provider, a chamber of commerce) can send its users into a Compass Connect
instance. The platform's server creates the user with an API key and gets back a hand-off link. The user opens the link
and is logged in to Compass, with no sign-up and no password.

This guide is for the developers of that platform. Each instance serves the full specification at `<BACKEND_URL>/docs`
(tag "Integration") and `<BACKEND_URL>/openapi.json`. Operators set the API up with the
[getting-started guide](../getting-started/README.md#optional-integration-api).

To try the flow, run [`example.mjs`](example.mjs), a quick example in one file with no dependencies (Node.js 20 or
later). Open http://localhost:3100, click **Build my profile**, and you land in Compass as the user of the form:

```bash
COMPASS_BACKEND_URL=http://localhost:8080 COMPASS_API_KEY=<a key from API_KEYS> node docs/integration/example.mjs
```

## How it works

1. The user clicks a button on your platform, for example "Build my profile".
2. Your server calls `POST /integration/users` with the user's `external_id` and `email`. The first time, Compass
   creates an account for the user. The response contains a hand-off link.
3. Your server redirects the user's browser to the link.
4. Compass logs the user in. On the first visit, the user accepts the Compass terms of use on the consent screen.
5. Compass opens the page that the `action` of the request asks for.

## Before you start

Ask the operator of the Compass instance for:

- **The backend URL** (`BACKEND_URL`), for example `https://api.compass.example.org`. It is usually a different
  address from the one users open in the browser.
- **An API key**, to send in the `x-api-key` header.

Call the API from your server only. Never put the key in a web page, a mobile app or a URL.

## Create a user: `POST /integration/users`

One user per call. Every call returns a new hand-off link.

| Field | Required | Description |
|---|---|---|
| `external_id` | yes | Your id for the user, 1 to 128 characters, case-sensitive. One `external_id` is one user on the instance. Use an internal id, not a national id number, a phone number or other personal data. |
| `email` | yes | The user's email. It becomes their Compass account and is stored in lower case. Compass sends no email when it creates the account. |
| `action` | no | Where the link takes the user. `skill_report` (default) opens the conversation that builds the skills report. `create` opens the Compass home page. |

A request with any other field (a name, a gender, an education level) gets `422`. Compass stores the `external_id`, the
email, the creation date and a SHA-256 hash of the link token, nothing else from your platform.

```bash
curl -i -X POST "$BACKEND_URL/integration/users" \
  -H "x-api-key: $API_KEY" -H "content-type: application/json" \
  -d '{"external_id": "PRM-000123", "email": "user123@example.org"}'
```

```json
{
  "result": "User created, hand-off link issued.",
  "user": {
    "external_id": "PRM-000123",
    "email": "user123@example.org",
    "created_at": "2026-10-20T14:03:12.345000Z"
  },
  "link": {
    "url": "https://compass.example.org/#/handoff?token=usxPzf7-dWASJmBY7cL9ixxROwKgRjHZdbQk1tN6Bgo",
    "expires_at": "2026-10-21T14:03:12.348211Z"
  }
}
```

`result` is a sentence for people and logs. Branch on the HTTP status. Times are UTC, in ISO 8601.

**Calling again.** A call with the same `external_id` and `email` returns `200`, the same user and a new link. It is
safe to repeat a call after a timeout or a `500`: the new call finishes what the earlier one started.

## Status codes

| Status | Meaning | What to do |
|---|---|---|
| `201` | Compass created the user. | Redirect the user to `link.url`. |
| `200` | The user already existed with this `external_id` and `email`. | Same as `201`. Earlier links of this user no longer work. |
| `403` | The `x-api-key` header is missing or not accepted. | Check the key with the operator. |
| `409` | The user cannot be created or opened. The `error_code` field of the body gives the reason (next table). | Repeating the same call gives the same answer. |
| `422` | The body is invalid. `detail` lists each problem. | Fix the request. |
| `500` | An unexpected error in Compass. | Repeat the call later. If it keeps failing, send the `correlation_id` of the response to the operator. |

| `error_code` | Meaning | What to do |
|---|---|---|
| `external_id_bound_to_other_email` | This `external_id` already belongs to a user with another email. | Send the email of the first call. The API cannot change a user's email: ask the operator. |
| `email_bound_to_other_external_id` | This email already belongs to a user with another `external_id`. | Check your platform for two records of the same person. |
| `account_already_exists` | The email has a Compass account that was not created through this API: the person signed up, or an operator created it. Compass does not take over such accounts. | The person logs in to Compass directly. |
| `account_not_eligible` | The account was created through this API, then disabled, deleted or given an administrator or staff role. | Contact the operator. |

## The hand-off link

- **It works until `link.expires_at`**, 24 hours by default (the operator can change this). The user can open it again
  after a reload, in another browser or on another device. Completing the conversation does not end it.
- **One live link per user.** Each call replaces the user's earlier link.
- **It is a credential.** Anyone who opens it before it expires is logged in as the user. Keep it out of your logs,
  analytics tools and error reports. The token sits after the `#`, which browsers do not send to servers, and Compass
  removes it from the address bar when the page opens.

Request the link when the user clicks, then redirect the browser to it (for example with `303 See Other`). A link
requested in advance stops working as soon as another call for the same user issues a new one.

What the user sees:

- **First visit:** the consent screen, then the page of the `action`.
- **Later visits:** the page of the `action`.
- **A Compass session already open in the browser** (another person on a shared device, or the same user): Compass
  logs it out, then logs in the user of the link.
- **An expired, replaced or unknown link:** a page titled "This link can't be used" that asks the user to go back to
  your platform, with a button to the Compass sign-in page.

## Not in this version

- **Results.** Fetching the skills report as JSON, a webhook when the conversation ends and the redirect back to your
  platform will come in a later version. It will add optional request fields; clients that do not send them will keep
  working.
- Several users in one call, changing a user's email, deleting a user.
- Choosing the language per user. The conversation uses the language of the instance.
