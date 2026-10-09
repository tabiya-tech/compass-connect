# Getting started: run Compass Connect on your own machine

This guide takes you from a fresh clone to a running Compass Connect (backend, frontend and a first conversation) on your own computer. Once it runs locally you have the basis to deploy it on the cloud provider you prefer.

You will end up with:

- the backend running at `http://localhost:8080`,
- the frontend running at `http://localhost:3000`,
- your first conversation and a skills report generated.

> **Scope.** This is a guide for local test environments, not for a production deployment. It was tested on macOS. The Windows (PowerShell) commands are written with care but have not been run on a Windows machine yet; if you use Windows, [WSL2](https://learn.microsoft.com/windows/wsl/) makes most of the steps easier. If something fails, please open an issue.
>
> **Docker.** This guide sets up the pieces by hand (a local MongoDB plus MongoDB Atlas for the vector search). A Docker-based self-hosted setup is on its way and will replace the Atlas parts of this guide.

## The pieces

- The **frontend** is a React application that talks to the backend.
- The **backend** is a Python server that uses four services:
  - a **MongoDB** database for the regular data: conversations, users, metrics.
  - a **vector database** to search embeddings. This guide uses MongoDB Atlas (free tier).
  - **Google Cloud (Vertex AI)**, which provides the language model (Gemini) and the embeddings used to search occupations and skills. Embeddings only work with Vertex AI today. Cloud DLP is used to protect personal data.
  - **Firebase** for the user login.

So you need:

- a Google Cloud account with a few services enabled (Firebase can live in the same project),
- a free MongoDB Atlas account.

## Prerequisites

Tools installed on your computer:

- Git
- Python 3.12
- Node.js 22
- MongoDB Community Server, `mongosh` and the MongoDB Database Tools
- [Poetry](https://python-poetry.org/) (Python packages) and [Yarn](https://yarnpkg.com/) (JavaScript packages)

```bash
# macOS
brew install git python@3.12 node@22 poetry yarn
brew tap mongodb/brew && brew install mongodb-community mongosh mongodb-database-tools
```

```powershell
# Windows 10/11
winget install Git.Git
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install MongoDB.Server
winget install MongoDB.Shell
winget install MongoDB.DatabaseTools
npm install --global yarn
pip install poetry
```

Then clone the repository:

```bash
git clone https://github.com/tabiya-tech/compass-connect.git
cd compass-connect
```

## Accounts

### 1. Google Cloud

You need a Google Cloud project with billing enabled to use the Vertex AI models. The cost of these first tests should be a few dollars at most. Everything here is done in the [Google Cloud console](https://console.cloud.google.com/).

1. Create a project and attach a billing account.
2. Create a [budget alert](https://console.cloud.google.com/billing/budgets) so you never overspend (for example 10 USD).
3. Enable these two APIs:
   - [Vertex AI](https://console.cloud.google.com/apis/library/aiplatform.googleapis.com) (it may appear as "Agent Platform API")
   - [Cloud Data Loss Prevention (DLP)](https://console.cloud.google.com/apis/library/dlp.googleapis.com)
4. Create a [service account](https://console.cloud.google.com/iam-admin/serviceaccounts) with the roles `roles/aiplatform.user` and `roles/dlp.user`.
5. Download its JSON key (Keys, Add key, JSON), create the `backend/keys` folder (it does not exist in a fresh clone) and save the key there as `backend/keys/credentials.json`. That folder is in `.gitignore`: never commit the key. The smoke test, the taxonomy setup and the backend `.env` all point to this path, so keep it unless you change them.

### 2. Firebase (login)

Use the same Google Cloud project.

1. Open the [Firebase console](https://console.firebase.google.com/) and add Firebase to your existing project.
2. In Authentication, Sign-in method, enable **Email/Password** and **Anonymous**.
3. Check that `localhost` is among the authorized domains (it usually is).
4. In Project settings, Your apps, register a web app and copy its `apiKey` and `authDomain`. The frontend needs them.

### 3. MongoDB Atlas

The vector search needs a database that supports it. Atlas has a free tier and is quicker than installing anything locally.

1. Create an **M0** (free) cluster in the region you prefer.
2. Create a database user with read and write permissions and keep the password. Use a password with only letters and numbers, special characters must be URL-encoded in the connection string (`@` becomes `%40`).
3. Atlas usually adds your current IP address to the allowed list when the cluster is created. If you later cannot connect, check Network Access and add your IP.
4. Click **Connect** on the cluster to find the connection string (`mongodb+srv://...`). Keep it, you will need it soon.

The free tier stores 512 MB, and the full taxonomy with embeddings is larger than that. That is why step 3 below offers a *partial* taxonomy.

## Set up Compass Connect

### Step 1: install the backend dependencies

```bash
cd backend
python -m venv venv-backend
source venv-backend/bin/activate        # Windows: .\venv-backend\Scripts\Activate.ps1
poetry sync
```

If a Python from conda or a `python` alias gets in the way, deactivate conda (`conda deactivate`) and call the virtual environment's Python directly (`venv-backend/bin/python`). If PowerShell refuses to run scripts, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` in a new window.

If PyPI times out on `onnxruntime` (a large package), retry with `POETRY_REQUESTS_TIMEOUT=300 poetry sync`.

To check the installation you can run the unit tests (they take several minutes):

```bash
poetry run pytest -m "not (evaluation_test or smoke_test or llm_integration)"
```

#### Check Google Cloud

Before going further, check that your project is ready. The test authenticates with the service-account key you saved as `backend/keys/credentials.json` in [Accounts, step 1](#1-google-cloud); that is the path it looks for when you run it from the `backend` folder. If your key is somewhere else, pass `--key path/to/credentials.json`. From the `backend` folder, with the virtual environment active:

```bash
python ../docs/getting-started/scripts/gcp_smoke_test.py
```

A successful run looks like this:

```
Project: your-project
Service account: your-sa@your-project.iam.gserviceaccount.com
Embeddings region: us-central1
Gen-AI region: global

  [OK] Embeddings text-embedding-005: 768 dimensions
  [OK] Gemini gemini-3.5-flash-lite (LLM_DEFAULT_MODEL): replied 'OK'
  [OK] Gemini gemini-3.8-flash (LLM_REASONING_MODEL): replied 'OK'
  [OK] Gemini gemini-3.1-pro-preview (LLM_DEEP_REASONING_MODEL): replied 'OK'
  [OK] Cloud DLP deidentify: 'write to [EMAIL_ADDRESS]'

5/5 checks passed
```

If a check fails, the message says what failed and a hint line suggests the usual causes (missing role, API not enabled, billing, quota). Do not continue until the 5 checks pass.

### Step 2: local MongoDB

This is where the backend stores everything it writes while you chat. It needs no special configuration. Just make sure it is running:

```bash
brew services start mongodb-community      # macOS
sudo systemctl start mongod                # Linux
Get-Service MongoDB                        # Windows (installed as a service)
```

```bash
mongosh "mongodb://127.0.0.1:27017" --eval "db.runCommand({ping:1})"
```

### Step 3: the taxonomy (vector search)

Compass Connect talks to the user and looks for their skills in the ESCO-based taxonomy published by Tabiya. That search is done with embeddings (vectors), so you need a copy of the taxonomy, with its embeddings, in your Atlas database.

One script does everything: it downloads the taxonomy from [taxonomy.tabiya.tech](https://taxonomy.tabiya.tech/#/modeldirectory), imports it into your local MongoDB, generates the embeddings with Vertex AI into Atlas, creates the vector search indexes, waits for them to be ready and runs a sample search.

It has two modes:

| Mode | What it loads | When to use it |
|---|---|---|
| `partial` (default) | all 3,074 occupations and the 5,500 most used skills (of 13,896) | the Atlas free tier (M0, 512 MB) |
| `full` | the whole taxonomy | a bigger cluster |

Occupation search is complete in `partial` mode. Only rare skills (used by one or two occupations) cannot be found.

From the repository root, with your Atlas connection string in an environment variable (so the password stays out of your shell history):

```bash
export TARGET_MONGODB_URI="mongodb+srv://user:password@your-cluster.mongodb.net/"   # Windows: $env:TARGET_MONGODB_URI = "..."
```

First a dry run, which downloads and validates the taxonomy and writes nothing:

```bash
backend/venv-backend/bin/python docs/getting-started/scripts/setup_taxonomy.py \
    --credentials backend/keys/credentials.json --mode partial
```

Then for real:

```bash
backend/venv-backend/bin/python docs/getting-started/scripts/setup_taxonomy.py \
    --credentials backend/keys/credentials.json --mode partial --hot-run
```

(On Windows use `backend\venv-backend\Scripts\python.exe` and replace the `\` line continuations with a backtick.)

The whole partial setup (download, import, embeddings, indexes ready) took about 7 minutes in our test on an empty Atlas M0, and it depends on your Vertex AI quota. The process can be repeated: it skips the embeddings it already generated, so if it is interrupted run the same command again. Vertex AI embeddings are billed. The partial taxonomy sends about 4.1 million characters (roughly 1 million tokens) to `text-embedding-005`, which at the published rates is an estimated 10 to 40 US cents (check the current [Vertex AI pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)). The budget alert you created in step 1 protects you from surprises.

At the end it prints the values for the backend `.env` (`TAXONOMY_MODEL_ID` and `TAXONOMY_DATABASE_NAME`) and a sample search like this:

```
"I sell vegetables at the market" -> occupations

  0.876  market vendor
  0.864  fruit and vegetables specialised seller
  0.843  wholesale merchant in fruit and vegetables
```

Similar results mean the vectors and the index are fine. Other options:

- `--taxonomy-url`: use another taxonomy export. The list of models is at [taxonomy.tabiya.tech](https://taxonomy.tabiya.tech/#/modeldirectory); the file name starts with the model id. Compass Connect is developed against the default one.
- `--skills-limit N`: how many skills `partial` mode keeps.
- `--target-db`: the database to write to (default `compass-taxonomy`).

The scripts it uses are in [`scripts/`](scripts/) and can be run separately: `import_taxonomy_csv.py` (CSV to a local MongoDB shaped like the Taxonomy Platform's), `generate_embeddings.py` (a wrapper around `backend/scripts/embeddings/generate_taxonomy_embeddings.py`) and `check_search.py` (a search like the backend's; try `python check_search.py "baking bread"`, or `--collection skills`). The taxonomy is in English, so search in English.

If the search returns nothing, check that `embedding_index` is **READY** in Atlas (Atlas M0 allows 3 search indexes, 2 are used by the taxonomy) and that the model id matches.

> **Important:** the embeddings of the taxonomy and the embeddings of the user's messages must come from the same model. The backend checks this at startup. The default is `text-embedding-005` (768 dimensions).

> **Attribution.** The default taxonomy is the "Tabiya (ESCO 1.1.1)" model published by Tabiya under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), based on ESCO v1.1.1 (c) European Union. This publication uses the [ESCO classification](http://ec.europa.eu/esco) of the European Commission. If you redistribute data derived from it, give attribution and indicate your changes (a partial taxonomy with embeddings is a modified version, not the official ESCO classification).

### Step 4: the backend `.env` file

```bash
cp .env.example .env
```

Set the values below and leave the others as they are. Find each variable in your `.env` and change its value (do not paste the whole block at the end of the file, to avoid duplicates). The taxonomy and career explorer variables point to **Atlas**; the others to your **local MongoDB**.

```ini
# --- Taxonomy: in Atlas ---
# If the password has special characters, URL-encode them (@ -> %40)
TAXONOMY_MONGODB_URI=mongodb+srv://user:password@your-cluster.mongodb.net/
TAXONOMY_DATABASE_NAME=compass-taxonomy
TAXONOMY_MODEL_ID=68933862382aab4c7de13ec6

# --- Career explorer: also in Atlas (same URI) ---
CAREER_EXPLORER_MONGODB_URI=mongodb+srv://user:password@your-cluster.mongodb.net/
CAREER_EXPLORER_DATABASE_NAME=compass-career-explorer

# --- Application data: in your local MongoDB (step 2) ---
APPLICATION_MONGODB_URI=mongodb://127.0.0.1:27017
APPLICATION_DATABASE_NAME=compass-application

USERDATA_MONGODB_URI=mongodb://127.0.0.1:27017
USERDATA_DATABASE_NAME=compass-userdata

METRICS_MONGODB_URI=mongodb://127.0.0.1:27017
METRICS_DATABASE_NAME=compass-metrics
BACKEND_ENABLE_METRICS=True

JOBS_MONGODB_URI=mongodb://127.0.0.1:27017
JOBS_DATABASE_NAME=compass-jobs
JOBS_COLLECTION_NAME=jobs

# --- Google Cloud ---
# Path to the service-account key (relative to the backend folder)
GOOGLE_APPLICATION_CREDENTIALS=keys/credentials.json
EMBEDDINGS_SERVICE_NAME=GOOGLE-VERTEX-AI
# Must match the model the taxonomy vectors were generated with
EMBEDDINGS_MODEL_NAME=text-embedding-005
VERTEX_API_EMBEDDINGS_REGION=us-central1
VERTEX_API_GEN_AI_REGION=global

# --- Run mode ---
LLM_PROVIDER=gemini
TARGET_ENVIRONMENT_TYPE=local
BACKEND_ENABLE_SENTRY=False
BACKEND_ENABLE_TRACING=False
# So you do not need a registration code the first time
GLOBAL_DISABLE_REGISTRATION_CODE=True

# --- Matching service: leave empty, but they must exist ---
MATCHING_SERVICE_URL=
MATCHING_SERVICE_API_KEY=
```

Three things that commonly go wrong:

1. **Delete or fill in every `<placeholder>`** left in `.env.example` (`<True/False>`, `<URL>`, ...). They can break the startup.
2. **Do not set `GOOGLE_CLOUD_PROJECT`.** The project is taken from the JSON key; if you set it, the Google client calls an API you have not enabled and floods the log with warnings.
3. **The two matching service variables must exist even if you do not use them.** If you remove them, the backend crashes at startup with a pydantic error ("Input should be a valid string").

#### Generate the offline optimization files

Without these files the frontend shows a confusing CORS error (the real error is a `FileNotFoundError` in the backend logs). Generate them from the `backend` folder with the virtual environment active (about a minute, no cloud calls):

```bash
cd app/agent/preference_elicitation_agent/offline_optimization
python run_offline_optimization.py --output-dir ../../../../offline_output
```

The backend reads them from `backend/offline_output/`.

### Step 5: start the backend

```bash
cd backend
venv-backend/bin/python app/server.py      # Windows: .\venv-backend\Scripts\python.exe app\server.py
```

Open <http://localhost:8080/docs>: Swagger must load. In the logs you should see it connect to the databases and validate the taxonomy model with `GOOGLE-VERTEX-AI - text-embedding-005`.

### Step 6: the frontend

In **another** terminal:

```bash
cd frontend-new
yarn install
cp public/data/env.example.js public/data/env.js      # Windows: Copy-Item
```

The frontend reads its configuration at runtime from `public/data/env.js`, and **every value is base64** (`btoa(...)`). The file is in `.gitignore`. Find each key and change its value as below, keeping the `btoa(...)`; leave the keys that are not listed.

```js
// --- Firebase: from your web app (account 2) ---
FIREBASE_API_KEY: btoa("the apiKey of your Firebase web app"),
FIREBASE_AUTH_DOMAIN: btoa("your-project.firebaseapp.com"),

// --- Backend ---
BACKEND_URL: btoa("http://localhost:8080"),
TARGET_ENVIRONMENT_NAME: btoa("local"),

// --- RSA public key (see below how to generate it) ---
SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY: btoa("your public key"),
SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY_ID: btoa("local-1"),

// --- Turn off what is not used locally ---
FRONTEND_ENABLE_SENTRY: btoa("false"),
FRONTEND_GTM_ENABLED: btoa("false"),
GLOBAL_ENABLE_CV_UPLOAD: btoa("false"),

// Metrics stay on
FRONTEND_ENABLE_METRICS: btoa("true"),

// The taxonomy of this guide is in English
FRONTEND_SUPPORTED_LOCALES: btoa(JSON.stringify(["en-US"])),

// Must match GLOBAL_DISABLE_REGISTRATION_CODE in the backend
GLOBAL_DISABLE_REGISTRATION_CODE: btoa("true"),
GLOBAL_DISABLE_LOGIN_CODE: btoa("true"),
```

The RSA keys (used to encrypt sensitive personal data) are generated **outside the repository**:

```bash
mkdir -p ~/.compass-keys && cd ~/.compass-keys
openssl genrsa -out private-key.pem 2048
openssl rsa -in private-key.pem -pubout -out public-key.pem
```

On Windows you can use the `openssl` that ships with Git (`C:\Program Files\Git\usr\bin\openssl.exe`).

The **public** key goes in `env.js`. The frontend strips the `BEGIN` and `END` lines and the line breaks, so the easiest way is to paste it on one line with only its content:

```bash
sed '1d;$d' public-key.pem | tr -d '\n'
```

Copy the output (it starts with `MIIB...`) into `env.js`:

```js
SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY: btoa("MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A..."),
```

The **private** key does not go in `env.js`. Keep it somewhere safe and never commit it. For local tests an unprotected key is fine; in production protect it with a passphrase. This comes from reading the frontend code: the complete sensitive data flow was not tested here.

Start the frontend:

```bash
BROWSER=none yarn start      # Windows: $env:BROWSER = "none"; yarn start
```

Open <http://localhost:3000>. You should see the login screen.

### Step 7: try it

1. **Register** with an email and password. Check that the user appears in the Firebase console, Authentication. You should receive an email from Firebase, check your spam folder.
2. Click **Start Profile Chat** and tell your experience (for example "I worked as a baker for 3 years"). Keep going until you see the summary of your skills.
3. **Be patient:** a full conversation takes a while (the welcome screen says about 50 minutes on average) and with the low quota of a new project it can be slow.

To check what was saved, look at the local databases with `mongosh`:

```bash
mongosh compass-userdata --eval "db.user_preferences.find().pretty()"
mongosh compass-application --eval "db.collect_experience_state.find().sort({_id:-1}).limit(1).pretty()"
mongosh compass-metrics --eval "db.metric_events.find().sort({_id:-1}).limit(10).pretty()"
```

The Vertex AI traffic of that session is visible in the Google Cloud console (Vertex AI, Dashboard).

## Keeping it running

The backend and the frontend are two processes that stay open: one terminal each. `mongod` runs as a service, so it does not need a terminal. If you launch them from a tool with a time limit, they stop on their own when it expires.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Frontend loads, the console shows a CORS error and a 500 on `/users/me/progress` | `backend/offline_output/` is missing (the real error is a `FileNotFoundError` in the backend logs) | Run `run_offline_optimization.py` (step 4) |
| Backend crashes at startup with a pydantic error about `matching_service_url` | The matching variables are absent from `.env` | Define `MATCHING_SERVICE_URL=` and `MATCHING_SERVICE_API_KEY=` empty |
| Startup problems with `<placeholder>` values | `.env.example` placeholders left in | Replace or delete them |
| Vertex warnings flood the log | `GOOGLE_CLOUD_PROJECT` is set | Remove it |
| Poetry creates a strange virtual environment, or `python` is not the one you expect | conda `base` is active, or a `python` alias | `conda deactivate`; call the virtual environment's Python directly |
| `429 Resource exhausted` from Gemini | Low quota on a new project | Wait (the backend retries), set `VERTEX_API_GEN_AI_REGION=global`, or request more quota |
| Timeout downloading `onnxruntime` | Large package | `POETRY_REQUESTS_TIMEOUT=300`, then `poetry sync` |
| Embedding call fails the first time | Vertex AI API not enabled | Enable it in the project |
| About 30 s delay, then "server selection timeout" | `mongod` is not running, or `localhost` resolves to IPv6 | Start it; use `127.0.0.1` in the URIs |
| Same error, only for the taxonomy | Your IP is missing from Atlas Network Access, or the Atlas password has special characters | Add the IP; use a letters-and-digits password or URL-encode it |
| Atlas "out of space" | M0 is 512 MB | Use `--mode partial` |
| No vector search results | `embedding_index` is not READY, or the model id is wrong | Wait for READY; check `TAXONOMY_MODEL_ID` |
