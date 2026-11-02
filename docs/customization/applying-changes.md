# Applying Changes

Each setting has a name in [`config/default.json`](../../config/default.json) (for example `modules.disabled`) and an
environment variable (for example `FRONTEND_DISABLED_MODULES`). Which one you edit depends on how you run Compass
Connect. The [reference](reference.md) lists the variable of each setting.

## With Docker (recommended)

1. Set the variables in the `.env` file at the root of the repository, the one the
   [getting-started guide](../getting-started/README.md#docker-setup) creates from `.env.example`. Write JSON values
   (lists and objects) on one line; single quotes around them are optional:

   ```bash
   FRONTEND_DISABLED_MODULES=["career_explorer","job_matching"]
   ```

2. Apply them from the root of the repository:

   ```bash
   docker compose up -d
   ```

   Compose recreates the containers whose settings changed. The frontend reads its settings when it starts, so no
   image rebuild is needed (`--build` is only for code changes).

3. Reload the page.

## Without Docker (local development)

1. Copy `config/default.json` to a file named after your deployment, for example `config/connect.json`.
2. Change the values in your file. Only the values you change need to be included: settings missing from your file
   keep the value already in the backend `.env` and the frontend `env.js`. `strings` is the exception: when your file
   has it, it replaces all the text overrides, so `"strings": {}` restores the built-in texts.
3. From the `config` directory, run the inject script:

   ```bash
   cd config
   python3 inject-config.py --config connect.json
   ```

   It writes the values into the backend `.env` and the frontend `public/data/env.js`. To apply only some sections,
   name them:

   ```bash
   python3 inject-config.py --config connect.json --namespaces branding auth
   ```

4. Restart the frontend and the backend.

## When a Change Does Not Show

- **Look at the browser console.** Settings that cannot be read, such as invalid JSON, are reported there, and the
  application keeps their default. So are unknown module ids and text overrides that name no existing text.
- **Check the names.** A misspelled variable or config key is silently ignored and its default is used. Compare it
  with the [reference](reference.md).
- **Check what was applied.** With Docker, the variable must be in the `.env` at the root of the repository; without
  Docker, look for it in `frontend-new/public/data/env.js` and the backend `.env`.
