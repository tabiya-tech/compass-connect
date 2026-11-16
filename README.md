<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="frontend-new/public/compass-connect-logo-light.svg"/>
    <img src="frontend-new/public/compass-connect-logo-dark.svg" alt="Compass Connect" width="400"/>
  </picture>
</h1>

**Compass Connect** is an open-source career guidance platform for jobseekers. It is built on
[Compass](https://github.com/tabiya-tech/compass), Tabiya's conversational tool for skills discovery, and adds career
exploration, career readiness modules, job matching, and an admin portal for the organizations that run it.

Ministries, training institutions, and NGOs that support jobseekers can run Compass Connect under their own name and
adapt it to their labor market.

## Contents

- [Features](#features)
- [Components](#components)
- [Related Repositories](#related-repositories)
- [Getting Started](#getting-started)
- [Customization](#customization)
- [Data Protection](#data-protection)
- [Documentation](#documentation)
- [Contribution Guidelines](#contribution-guidelines)
- [License](#license)
- [Funders and Partners](#funders-and-partners)

## Features

### For Jobseekers

A deployment offers jobseekers the modules below. Operators can hide the modules they do not use (see
[Modules](docs/customization/modules.md)).

| Module | What the jobseeker does |
|---|---|
| Build your profile | Talks with the AI about formal and informal work. The conversation produces a skills report. |
| Career Explorer | Explores sectors and careers, with salary data and qualification routes. |
| Career Readiness | Works through guided modules on CVs, cover letters, interviews, workplace readiness, and entrepreneurship. |
| Knowledge Hub | Reads sector profiles, salary benchmarks, and qualification pathways. |
| Job Matching | Sees job openings matched to their skills. |

The skills report can be downloaded as a PDF or a Word document.

### For the Organizations That Run It

| Feature | What it does |
|---|---|
| Admin portal | Administrators and instructors manage users and view analytics in the [admin portal](admin-frontend). An instructor sees one institution. An administrator sees all of them. See [Admin & Instructor Registration](admin-registration.md). |
| Configuration | Modules, interface texts, branding, languages, sign-in, and the skills report are set in one `.env` file, with no code changes. See the [Customization Guide](docs/customization/README.md). |
| Integration API | A job portal or a training provider can send its users into Compass Connect and fetch their results. See the [integration guide](docs/integration/README.md). |
| Channels API | Telegram and WhatsApp bots can connect to Compass Connect. See the [channels guide](docs/channels/README.md). |
| Analytics | The backend provides analytics endpoints (`/analytics/*`). The [Compass Analytics](https://github.com/tabiya-tech/compass-analytics) dashboard reads them. |

## Components

- **[Frontend](frontend-new)** and **[admin frontend](admin-frontend)**: React and TypeScript applications.
- **[Backend](backend)**: a Python server built with FastAPI. It runs the AI agents and the APIs.
- **Database**: MongoDB for conversations, users, and metrics, with vector search for occupations and skills.
- **Language model**: Gemini on Vertex AI by default. The Anthropic Claude API and local models through Ollama can be
  selected with `LLM_PROVIDER`.
- **Other cloud services**: Vertex AI for embeddings, Google Cloud Data Loss Prevention, and Firebase for user login.
  Embeddings work only with Vertex AI today.
- **[Infrastructure as code](iac)**: Pulumi programs for a deployment on Google Cloud.

The architecture of the skills conversation is documented in the
[Compass repository](https://github.com/tabiya-tech/compass#architecture-overview).

## Related Repositories

Compass Connect brings together several of Tabiya's open-source tools. Each tool is developed in its own repository.
Most of them can also be used without Compass Connect. The code in all of them is open source under the MIT License.

| Repository | What it is | How Compass Connect uses it |
|---|---|---|
| [compass](https://github.com/tabiya-tech/compass) | Compass, the skills discovery conversation as a standalone application | Compass Connect is built on the Compass codebase. The conversation is the "Build your profile" module. |
| [taxonomy-model-application](https://github.com/tabiya-tech/taxonomy-model-application) | The Open Taxonomy Platform, which hosts and publishes taxonomy models such as the Inclusive Livelihoods Taxonomy | Required. On the first start, Compass Connect downloads a taxonomy export from the platform (`TAXONOMY_URL`) and builds its occupation and skill search from it. |
| [matching-engine](https://github.com/tabiya-tech/matching-engine) | The Tabiya Matching Engine, which ranks occupations and job openings against a jobseeker's skills and preferences | Optional. The Job Matching module calls the engine's API (`MATCHING_SERVICE_URL`). |
| [tabiya-livelihoods-classifier](https://github.com/tabiya-tech/tabiya-livelihoods-classifier) | The Livelihoods Classifier, which extracts occupations and skills from text and links them to taxonomy entries | Optional. The conversation can link skills through the classifier's API (`BACKEND_SKILL_LINKER=classifier`). The default is an LLM pipeline. |
| [compass-analytics](https://github.com/tabiya-tech/compass-analytics) | The analytics dashboard for partners and funders | Optional. The dashboard reads the analytics endpoints of a Compass Connect deployment (`/analytics/*`) with an API key. |

## Getting Started

You need [Docker](https://docs.docker.com/engine/install/) with Compose v2, Git, a Google Cloud project with Vertex AI
and Cloud Data Loss Prevention enabled, and a Firebase project for user login.

```bash
git clone https://github.com/tabiya-tech/compass-connect.git
cd compass-connect
cp .env.example .env    # fill the REQUIRED section
docker compose up -d --build
```

Then open <http://localhost:3000>. The first start downloads a taxonomy from the Open Taxonomy Platform and builds
the search index. In the default `partial` mode this takes about 7 minutes and an estimated 10 to 40 US cents of Vertex
AI usage.

The [getting-started guide](docs/getting-started/README.md) explains every step, including a setup without Docker.
For a deployment on Google Cloud, follow the [deployment procedure](deployment-procedure.md) and the
[deployment checklist](deployment-checklist.md).

## Customization

| What | For example | Guide |
|---|---|---|
| Modules | Offer only the skills conversation; hide Job Matching | [modules.md](docs/customization/modules.md) |
| Interface texts | Reword the home page introduction; name your own partners | [texts.md](docs/customization/texts.md) |
| Branding | Name, country, logos, colors, fonts, legal documents | [branding.md](docs/customization/branding.md) |
| Languages | Languages of the interface and of the conversation | [languages.md](docs/customization/languages.md) |
| Sign-in and registration | Login-only access; the personal data form | [sign-in.md](docs/customization/sign-in.md) |
| Skills report | Logos, formats, which details it shows | [skills-report.md](docs/customization/skills-report.md) |
| Web analytics | Google Analytics 4 through Google Tag Manager | [analytics.md](docs/customization/analytics.md) |

The interface is translated into `en-GB`, `en-US`, `es-ES`, `es-AR`, `sw-KE`, `ny-ZM`, and `pt-MZ`. To add a language,
follow [add-a-new-language.md](add-a-new-language.md).

Some adaptations to a country's labor market are not settings: the taxonomy, the sectors, the training curricula, and
the job sources. See [Adapting to Your National Context](docs/customization/national-context.md).

## Data Protection

- The personal data that users enter after registration is encrypted in the browser with an RSA public key. Decrypting
  it requires the private key, which the operator keeps. See [Sensitive Data Protection](sensitive-data-protection.md).
- Operators choose which personal data fields the form asks for, and supply their own legal documents.
- The backend can replace personal details in a user's message, such as names and phone numbers, with placeholders
  through Google Cloud Data Loss Prevention.

Each operator is responsible for complying with the data protection laws of the country where it runs Compass Connect.

## Documentation

| Topic | Where |
|---|---|
| Run it locally, with Docker or step by step | [docs/getting-started](docs/getting-started/README.md) |
| Customize a deployment | [docs/customization](docs/customization/README.md) |
| Connect an existing platform | [docs/integration](docs/integration/README.md) |
| Connect a chat bot | [docs/channels](docs/channels/README.md) |
| Backend | [backend](backend) |
| Frontend | [frontend-new](frontend-new) |
| Admin frontend | [admin-frontend](admin-frontend) |
| Infrastructure as code | [iac](iac) |
| Deploy to Google Cloud | [deployment-procedure.md](deployment-procedure.md), [deployment-checklist.md](deployment-checklist.md) |
| Sensitive data protection | [sensitive-data-protection.md](sensitive-data-protection.md) |
| Admin and instructor registration | [admin-registration.md](admin-registration.md) |
| Invitation codes for jobseekers | [invitations.md](invitations.md) |
| Add a language | [add-a-new-language.md](add-a-new-language.md) |

## Contribution Guidelines

Contributions are welcome: bug reports and suggestions as GitHub issues, and code, tests, documentation, and
translations as pull requests.

### Set Up

The scripts need a bash-compatible terminal (Linux, macOS, or Cygwin). They do not work in Windows cmd or PowerShell.

1. Fork the repository, clone it, and create a branch for your changes.
2. Set up the subproject you work on. For example, for `backend/` follow [backend/README.md](backend/README.md).
3. Before you open a pull request, run the checks:

    ```bash
    ./run-before-merge.sh
    ```

    The script checks formatting, lints, builds, and tests every subproject. A common cause of errors is an
    incomplete step 2.

4. Commit with [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) messages, push to your fork,
   and open a pull request to `main`.

### Code Style

- **Frontend**: [Prettier](https://prettier.io/), configured in
  [frontend-new/.prettierrc.json](frontend-new/.prettierrc.json).
- **Backend**: the [PEP 8 Style Guide](https://peps.python.org/pep-0008/), checked with pylint and `pylint-pydantic`,
  configured in [backend/.pylintrc](backend/.pylintrc).

In IntelliJ IDEA or PyCharm, restart the IDE after you change either configuration.

### Tests

We aim for 100 percent code coverage. See the
[Guidelines for Readable BDD Testing](testing-guidelines.md) and the
[Snapshot Testing Guidelines](snapshot-testing-guidelines.md).

Golden tests are end-to-end conversation tests. They check the agents' behavior against curated cases that represent
different user personas and scenarios. Run them from `backend/`:

```bash
# The whole golden test suite
poetry run pytest -m "golden_test" evaluation_tests/test_golden_set.py

# Specific golden tests
poetry run pytest -m "golden_test" evaluation_tests/test_golden_set.py \
  -k "golden_simple_formal_employment or golden_volunteer_student"

# A baseline metrics report, for regression tracking
poetry run python evaluation_tests/generate_baseline_report.py

# Replay golden transcripts and collect metrics (CI gating)
poetry run python evaluation_tests/golden_transcript_runner.py \
  --transcripts-dir evaluation_tests/golden_transcripts \
  --output-dir evaluation_tests/golden_transcripts/output

# Validate the metrics against the thresholds
poetry run python evaluation_tests/check_metrics_thresholds.py \
  --transcripts-dir evaluation_tests/golden_transcripts \
  --metrics-dir evaluation_tests/golden_transcripts/output
```

Test outputs are saved to `backend/evaluation_tests/test_output/`, in one timestamped folder per run.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more information.

## Funders and Partners
<img src="frontend-new/public/logo_Google.org_Support_FullColor_cmyk%20coated_stacked.png" alt="Google.org Logo" width=200/>

This project is tested with BrowserStack.
