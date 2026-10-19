// A partner platform in one file, to try the Compass integration API.
// No dependencies, Node.js 20 or later:
//
//   COMPASS_BACKEND_URL=http://localhost:8080 COMPASS_API_KEY=<a key from API_KEYS> node example.mjs
//
// Then open http://localhost:3100. The page posts the form to this server, the server calls
// POST /integration/users with the API key and redirects the browser to the hand-off link.
// The key stays on the server: never put it in a web page.
import { createServer } from "node:http";

const BACKEND_URL = (process.env.COMPASS_BACKEND_URL ?? "http://localhost:8080").replace(/\/$/, "");
const API_KEY = process.env.COMPASS_API_KEY;
const PORT = Number(process.env.PORT ?? 3100);

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
        <option value="skill_report">skill_report: the conversation that builds the skills report</option>
        <option value="create"${user.action === "create" ? " selected" : ""}>create: the Compass home page</option>
      </select>
    </label>
    <button type="submit">Build my profile</button>
  </form>
</body>
</html>`);
}

function escape(text) {
  return String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}
