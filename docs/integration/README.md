# Compass Connect integration API

It is possible to use Compass Connect as an additional module from your existing platforms, In thi scenario a external platform 
can send its users into a Compass Connect instance. 

The platform's server creates the user with an API key and gets back a hand-off link. The user opens the link
and is logged in to Compass, with no sign-up and no password.

Compass connects exposes the full API specification at `<BACKEND_URL>/docs`
(tag "Integration") and `<BACKEND_URL>/openapi.json`. Make sure you have looked at
[getting-started guide](../getting-started/README.md#optional-integration-api) to understand where your API key will come from.

To try the flow, run the [example integration](#example-integration) at the end of this guide.

## How it works

1. The user clicks a button on your platform, for example "Build my profile".
2. Your server calls `POST /integration/users` with the user's `external_id` and `email`. The first time, Compass
   creates an account for the user. The response contains a hand-off link.
3. Your server redirects the user's browser to the link.
4. Compass logs the user in. On the first visit, the user accepts the Compass terms of use on the consent screen.
5. Compass opens the page that the `action` of the request asks for.
6. When the conversation ends, a button sends the user back to the `return_url` of the request, on your platform.
7. Your server fetches what the conversation produced with `GET /integration/users/{external_id}/results`.

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
| `external_id` | yes | Your id for the user, 1 to 128 characters, case-sensitive: letters, digits and `.` `_` `:` `@` `-`. It cannot be `.` or `..`. One `external_id` is one user on the instance, and it is part of the [results](#get-the-results-get-integrationusersexternal_idresults) URL. Use an internal id, not a national id number, a phone number or other personal data. |
| `email` | yes | The user's email. It becomes their Compass account and is stored in lower case. Compass sends no email when it creates the account. |
| `action` | no | Where the link takes the user. `build_profile` (default) opens the conversation that builds the skills report. `create` opens the Compass home page. |
| `return_url` | no | Where the user goes back to when the conversation ends. See [Return URL](#return-url). |

A request with any other field (a name, a gender, an education level) gets `422`. Compass stores the `external_id`, the
email, the creation date, the `return_url` and a SHA-256 hash of the link token, nothing else from your platform.

```bash
curl -i -X POST "$BACKEND_URL/integration/users" \
  -H "x-api-key: $API_KEY" -H "content-type: application/json" \
  -d '{"external_id": "EXT-000123", "email": "user123@example.org",
       "return_url": "https://jobs.example.org/profile"}'
```

```json
{
  "result": "User created, hand-off link issued.",
  "user": {
    "external_id": "EXT-000123",
    "email": "user123@example.org",
    "return_url": "https://jobs.example.org/profile",
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
| `422` | The body is invalid, or its `return_url` is not allowed on the instance. `detail` lists each problem. | Fix the request. |
| `500` | An unexpected error in Compass. | Repeat the call later. If it keeps failing, send the `correlation_id` of the response to the operator. |

| `error_code` | Meaning | What to do |
|---|---|---|
| `external_id_bound_to_other_email` | This `external_id` already belongs to a user with another email. | Send the email of the first call. The API cannot change a user's email: ask the operator. |
| `email_bound_to_other_external_id` | This email already belongs to a user with another `external_id`. | Check your platform for two records of the same person. |
| `account_already_exists` | The email has a Compass account that was not created through this API: the person signed up, or an operator created it. Compass does not take over such accounts. | The person logs in to Compass directly. |
| `account_not_eligible` | The account was created through this API, then disabled, deleted or given an administrator or staff role. | Contact the operator. |

## Return URL

When the conversation ends, Compass shows the user a button back to your platform: "Back to jobs.example.org",
named after the host of the `return_url`. The button opens the `return_url` in the same tab. Users without a
`return_url` do not see it.

- **The operator allows your origins.** The scheme, host and port of the `return_url` must be in the instance's
  allow-list, or the call gets `422` and Compass creates nothing. Ask the operator to add your origin, for example
  `https://jobs.example.org`. The URL must use `https`; `http` works only for `localhost` and `127.0.0.1`.
- **Each call replaces it.** A call without `return_url` removes it. Send it on every call if you want the button.
- **Compass adds nothing to it.** Put what your page needs in the URL yourself, for example
  `https://jobs.example.org/profile?compass=1`. The `external_id` is not added: your server knows which user came
  back from its own session.
- Up to 2048 characters.

When the user comes back, your server can [fetch the results](#get-the-results-get-integrationusersexternal_idresults).

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

## Get the results: `GET /integration/users/{external_id}/results`

What the user's conversations produced: whether each one is completed, and the experiences and skills the user
explored. Call it from your server with the same `x-api-key`, for example when the user comes back through the
[return URL](#return-url).

```bash
curl -s "$BACKEND_URL/integration/users/EXT-000123/results" -H "x-api-key: $API_KEY"
```

```json
{
  "external_id": "EXT-000123",
  "email": "user123@example.org",
  "conversations": [
    {
      "session_id": 243308803207305,
      "conversation_completed": true,
      "conversation_conducted_at": "2026-10-22T16:41:08.120000Z",
      "experiences": [
        {
          "UUID": "3885d39e-3730-47e4-ab36-93f327e2c667",
          "experience_title": "Shop assistant",
          "normalized_experience_title": "Shop assistant",
          "company": "Corner Hardware Store",
          "location": "Springfield",
          "timeline": {"start": "2023-01", "end": "2024-06"},
          "work_type": "FORMAL_SECTOR_WAGED_EMPLOYMENT",
          "summary": "Served customers at the counter, ran the till and kept the stock records.",
          "exploration_phase": "PROCESSED",
          "top_skills": [
            {
              "UUID": "f666cb4d-e30e-4b9c-b531-adca789ee5dc",
              "preferredLabel": "assist customers",
              "altLabels": ["serve customers"],
              "description": "Help customers find the products they need...",
              "orderIndex": 0
            }
          ],
          "remaining_skills": []
        }
      ]
    }
  ]
}
```

- **`conversations`**: one per conversation of the user, newest first. A user has one conversation unless they start
  a new one in Compass. Use the first entry with `conversation_completed: true`. A user who has not started yet
  has one entry with `conversation_completed: false`, `conversation_conducted_at: null` and no experiences.
- **`conversation_conducted_at`**: the time of the last turn. For a completed conversation, the time it ended.
- **`experiences`**: the experiences as the user sees them in Compass, with their edits, and without the ones they
  deleted. Experiences still being explored are left out. The list grows while the conversation goes on.
  `work_type` is `FORMAL_SECTOR_WAGED_EMPLOYMENT`, `FORMAL_SECTOR_UNPAID_TRAINEE_WORK` or `UNSEEN_UNPAID` (volunteering,
  caregiving, household work). The text fields can be `null`. The `timeline` is in the words the user used.
- **`top_skills`**: the skills shown on the user's skills report, in order. `remaining_skills` holds the other skills
  found for the experience. Labels and descriptions come from the instance's taxonomy, in its language. The skill
  `UUID` is the taxonomy's id for the skill.
- **The results can change.** The user can still edit and delete experiences after the conversation ends. Each call
  returns the current state; fetch them again when you need them up to date.

| Status | Meaning |
|---|---|
| `200` | The results, as above. |
| `403` | The `x-api-key` header is missing or not accepted. |
| `404` | No user with this `external_id` on the instance. |
| `422` | The `external_id` in the path is not valid. |

## Not in this version

- **A webhook when the conversation ends.** Until then, fetch the results when the user comes back, or check them
  from time to time.
- The skills report as a PDF. The results above hold its content.
- Several users in one call, changing a user's email, deleting a user.
- Choosing the language per user. The conversation uses the language of the instance.

## Example integration

A minimal partner platform in a single JavaScript file, with no dependencies (Node.js 20 or later). Save the code
below as `example.mjs` and run it with a key from `API_KEYS` of your Compass instance (`COMPASS_BACKEND_URL` defaults
to `http://localhost:8080`):

```bash
COMPASS_BACKEND_URL=http://localhost:8080 COMPASS_API_KEY=<a key from API_KEYS> node example.mjs
```

Open http://localhost:3100, click **Build my profile**, and you land in Compass as the user of the form. When the
conversation ends, the button in Compass brings you back to http://localhost:3100/return, which shows the results. The
return button needs `http://localhost:3100` in the instance's allow-list: ask the operator, or see the
[getting-started guide](../getting-started/README.md#optional-integration-api).

```javascript
// A partner platform in one file, to try the Compass integration API.
// No dependencies, Node.js 20 or later:
//
//   COMPASS_BACKEND_URL=http://localhost:8080 COMPASS_API_KEY=<a key from API_KEYS> node example.mjs
//
// Then open http://localhost:3100. The page posts the form to this server, the server calls
// POST /integration/users with the API key and redirects the browser to the hand-off link.
// When the conversation ends, the button in Compass brings the browser back to /return, which fetches
// the results. The operator must allow http://localhost:3100 in BACKEND_INTEGRATION_RETURN_URL_ORIGINS.
// The key stays on the server: never put it in a web page.
import { createServer } from "node:http";

const BACKEND_URL = (process.env.COMPASS_BACKEND_URL ?? "http://localhost:8080").replace(/\/$/, "");
const API_KEY = process.env.COMPASS_API_KEY;
const PORT = Number(process.env.PORT ?? 3100);
const PUBLIC_URL = `http://localhost:${PORT}`;

if (!API_KEY) {
  console.error("Set COMPASS_API_KEY to one of the keys in API_KEYS of the Compass instance.");
  process.exit(1);
}

createServer(async (req, res) => {
  if (req.method === "POST" && req.url === "/handoff") {
    const form = new URLSearchParams(await readBody(req));
    const user = {
      external_id: form.get("external_id")?.trim(),
      email: form.get("email")?.trim(),
      action: form.get("action"),
    };
    // A real platform knows who comes back from its own session. This example has no session, so it puts the
    // external_id in its own return URL.
    user.return_url = `${PUBLIC_URL}/return?external_id=${encodeURIComponent(user.external_id ?? "")}`;

    let response;
    try {
      response = await fetch(`${BACKEND_URL}/integration/users`, {
        method: "POST",
        headers: { "x-api-key": API_KEY, "content-type": "application/json" },
        body: JSON.stringify(user),
      });
    } catch (e) {
      return sendPage(res, 502, user, `Cannot reach ${BACKEND_URL}: ${e.message}`);
    }
    const body = await response.json().catch(() => ({}));

    // 201 (new user) and 200 (existing user) both carry a fresh link: send the browser there.
    // Do not log the link, it logs the user in.
    if (response.status === 201 || response.status === 200) {
      res.writeHead(303, { location: body.link.url }).end();
      return;
    }

    // 422 lists one problem per field, the other errors have a sentence
    const detail = Array.isArray(body.detail)
      ? body.detail.map((e) => `${e.loc.at(-1)}: ${e.msg}`).join("\n")
      : body.detail;
    const error = [`Compass answered ${response.status}`,
      body.error_code && `error_code: ${body.error_code}`,
      detail,
      body.correlation_id && `correlation_id: ${body.correlation_id}`].filter(Boolean).join("\n");
    return sendPage(res, response.status, user, error);
  }

  if (req.method === "GET" && req.url.startsWith("/return")) {
    const externalId = new URL(req.url, PUBLIC_URL).searchParams.get("external_id") ?? "";
    let response;
    try {
      response = await fetch(`${BACKEND_URL}/integration/users/${encodeURIComponent(externalId)}/results`, {
        headers: { "x-api-key": API_KEY },
      });
    } catch (e) {
      return sendResults(res, 502, externalId, null, `Cannot reach ${BACKEND_URL}: ${e.message}`);
    }
    const body = await response.json().catch(() => ({}));
    if (response.status !== 200) {
      return sendResults(res, response.status, externalId, null, `Compass answered ${response.status}: ${body.detail}`);
    }
    return sendResults(res, 200, externalId, body);
  }

  sendPage(res, 200, {});
}).listen(PORT, () => console.log(`Partner platform on http://localhost:${PORT}, calling ${BACKEND_URL}`));

function readBody(req) {
  return new Promise((resolve) => {
    let data = "";
    req.on("data", (chunk) => (data += chunk));
    req.on("end", () => resolve(data));
  });
}

// In a real platform the user is already logged in: the external_id and the email come from its session,
// and the page only has the button.
function sendPage(res, status, user, error) {
  res.writeHead(status, { "content-type": "text/html; charset=utf-8" }).end(`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Partner platform</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 480px; margin: 48px auto; padding: 0 16px; }
    label { display: block; margin-bottom: 16px; }
    input, select { display: block; width: 100%; padding: 8px; margin-top: 4px; box-sizing: border-box; }
    button { padding: 10px 16px; }
    .error { background: #fdecea; border: 1px solid #f5c2c0; padding: 12px; margin-bottom: 16px; white-space: pre-wrap; }
  </style>
</head>
<body>
  <h1>Partner platform</h1>
  <p>Pretend you are logged in to a job portal. The button sends you into Compass as this user.</p>
  ${error ? `<div class="error">${escape(error)}</div>` : ""}
  <form method="post" action="/handoff">
    <label>External id <input name="external_id" required maxlength="128" value="${escape(user.external_id ?? "test-user-1")}"></label>
    <label>Email <input name="email" type="email" required value="${escape(user.email ?? "test-user-1@example.org")}"></label>
    <label>Open
      <select name="action">
        <option value="build_profile">build_profile: the conversation that builds the skills report</option>
        <option value="create"${user.action === "create" ? " selected" : ""}>create: the Compass home page</option>
      </select>
    </label>
    <button type="submit">Build my profile</button>
  </form>
</body>
</html>`);
}

// What the platform would store in its own profile of the user: the latest completed conversation.
function sendResults(res, status, externalId, results, error) {
  const completed = results?.conversations.find((c) => c.conversation_completed);
  const experiences = (completed?.experiences ?? []).map((e) => `
    <li><strong>${escape(e.experience_title ?? "")}</strong>${e.company ? `, ${escape(e.company)}` : ""}
      <ul>${e.top_skills.map((s) => `<li>${escape(s.preferredLabel)}</li>`).join("")}</ul>
    </li>`).join("");
  res.writeHead(status, { "content-type": "text/html; charset=utf-8" }).end(`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Partner platform</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 640px; margin: 48px auto; padding: 0 16px; }
    .error { background: #fdecea; border: 1px solid #f5c2c0; padding: 12px; white-space: pre-wrap; }
    pre { background: #f4f4f4; padding: 12px; overflow-x: auto; font-size: 12px; }
  </style>
</head>
<body>
  <h1>Welcome back, ${escape(externalId)}</h1>
  ${error ? `<div class="error">${escape(error)}</div>` : ""}
  ${results && !completed ? "<p>The conversation is not completed yet.</p>" : ""}
  ${completed ? `<p>Conversation completed. Experiences and top skills:</p><ul>${experiences}</ul>` : ""}
  ${results ? `<details><summary>Full response</summary><pre>${escape(JSON.stringify(results, null, 2))}</pre></details>` : ""}
  <p><a href="/">Back to the form</a></p>
</body>
</html>`);
}

function escape(text) {
  return String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}
```
