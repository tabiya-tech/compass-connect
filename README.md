<h1 align="center">
<img src="https://raw.githubusercontent.com/tabiya-tech/compass-connect/refs/heads/main/frontend-new/public/compass-connect-logo-light.svg#gh-dark-mode-only" alt="logo" width=400/>
<img src="https://raw.githubusercontent.com/tabiya-tech/compass-connect/refs/heads/main/frontend-new/public/compass-connect-logo-dark.svg#gh-light-mode-only" alt="logo" width=400/>
</h1>

**Compass Connect** is an open-source career guidance platform for jobseekers. It is built on
[Compass](https://github.com/tabiya-tech/compass), Tabiya's conversational tool for skills discovery, and adds career exploration, career
readiness modules, job matching, and an admin portal for the organizations that run it.

A deployment offers jobseekers the modules below. Operators can hide the modules they do not use (see
[Modules](docs/customization/modules.md)).

| Module | What the jobseeker does |
|---|---|
| Build your profile | Talks with the AI about formal and informal work. The conversation produces a skills report. |
| Career Explorer | Explores sectors and careers, with salary data and qualification routes. |
| Career Readiness | Works through guided modules on CVs, cover letters, interviews, workplace readiness, and entrepreneurship. |
| Knowledge Hub | Reads sector profiles, salary benchmarks, and qualification pathways. |
| Job Matching | Sees job openings matched to their skills. |

Administrators and instructors manage users and view analytics in the [admin portal](admin-frontend). Other platforms
can send their users into Compass Connect through the [integration API](docs/integration/README.md). Telegram and
WhatsApp bots can connect through the [channels API](docs/channels/README.md).

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
| [docs](https://github.com/tabiya-tech/docs) | The source of [docs.tabiya.org](https://docs.tabiya.org) | Documentation of Tabiya's approach and products. |

## Table of Contents

- **[Getting Started](docs/getting-started/README.md)**: Run Compass Connect on your own machine, with Docker or step by step.

- **[Backend](backend)**: Explore the Backend directory for detailed insights about the backend project.

- **[Frontend](frontend-new)**: Explore the Frontend directory for detailed insights about the frontend project.

- **[Infrastructure As Code (IaC)](iac)**: Explore the Infrastructure as code(IAC) directory for detailed insights about
  the infrastructure-as-code components.

- **[Sensitive Data Protection](sensitive-data-protection.md)**: Explore the sensitive data protection functionality for detailed insights about how we are safeguarding sensitive personal data.

- **[Admin Frontend](admin-frontend)**: Explore the admin portal for managing users and viewing analytics.

- **[Admin & Instructor Registration](admin-registration.md)**: How super admins, cross-institution admins, and instructors are registered, approved, and bootstrapped per environment.

- **[Customization Guide](docs/customization/README.md)**: Explore the customization options for detailed insights about how partners can configure branding, themes, and feature availability.

- **[Integration API](docs/integration/README.md)**: How an existing platform sends its users into Compass Connect and fetches their results.

- **[Channels API](docs/channels/README.md)**: How Telegram and WhatsApp bots connect to Compass Connect.


## Architecture Overview
The images below show a high level overview of the solution architecture of Compass Connect.

![Compass Connect Architecture Overview](https://lucid.app/publicSegments/view/a1c21a2d-162b-4eae-b70a-f57b44181aa1/image.png)

![Compass Connect Cloud Architecture](https://lucid.app/publicSegments/view/fb45c622-0edb-4257-84a3-6fc4996692f3/image.png)

![Compass Connect Backend Architecture](https://lucid.app/publicSegments/view/3e5323ab-786b-4d46-bb73-dd716cdd9ee0/image.png)

![Compass Connect AI Architecture](https://lucid.app/publicSegments/view/db45dc1c-b89e-4ae4-bd32-347092693844/image.png)

## Why Contribute?

- **Make an Impact:** Your contributions will directly improve the user experience and functionality of Compass Connect, helping job-seekers explore and discover their skills more effectively.
- **Help Achieve Our Goals:** By contributing, you are supporting Compass Connect’s mission to populate digital skill wallets and guide job-seekers in understanding their skills and interests based on their lived experiences.

## Ways to Contribute

1. **Reporting Issues:** If you encounter bugs or have suggestions, open an issue on GitHub. Your feedback is valuable.
2. **Code Contributions:** Help enhance the codebase by submitting pull requests.
3. **Write or Improve Tests:** We aim for 100% code coverage. You can help achieve this goal by writing or improving tests.
4. **Documentation:** Improve project documentation by submitting pull requests. Clear documentation is crucial for new contributors.
5. **Add a New Language**: Help make Compass Connect accessible to more users by adding support for a new language. Follow the guidelines in [add-a-new-language.md](./add-a-new-language.md).
6. **Support:** Give the project a star on GitHub—your support encourages us to keep improving!

## Contribution Guidelines

🎉 Thank you for considering contributing to Tabiya Compass Connect! 🎉

### Code Formatting

### Frontend
We follow the **[Prettier](https://prettier.io/)** code formatting guidelines to make sure the code is properly formatted in a uniform way.

You can find the configuration in the **[.prettierrc.json](frontend-new/.prettierrc.json)** file.

> **Note:**  
> For IntelliJ IDEA, if you make changes to the Prettier config, you may need to restart the IDE before formatting code using the IDE’s formatting function.

### Backend
We follow the **[PEP 8 Style Guide](https://peps.python.org/pep-0008/)** to ensure the backend Python code is properly formatted in a consistent way.

We use **pylint** (with `pylint-pydantic`) as our linting tool.

You can find the configuration in the **[.pylintrc](backend/.pylintrc)** file.

> **Note:**  
> For IntelliJ IDEA / PyCharm, if you make changes to the linting configuration, you may need to restart the IDE before formatting or linting code using the IDE’s built-in tools.

### Conventional Commits

Please follow the **[Conventional Commits](https://www.conventionalcommits.org/)** format for commit messages.

### Guidelines for Readable BDD Testing

To contribute to our 100% code coverage goal, refer to our "Guidelines for Readable BDD Testing" in the **[testing-guidelines.md](testing-guidelines.md)**

### Guidelines for Snapshot Testing
To ensure component stability, refer to our "Snapshot Testing Guidelines" in the **[snapshot-testing-guidelines.md](snapshot-testing-guidelines.md)**

### Golden Tests & Evaluation Metrics

Golden tests are end-to-end conversation tests that validate the agent's behavior against curated test cases representing different user personas and scenarios.

**Run the golden test suite** (from `backend/`):

```bash
poetry run pytest -m "golden_test" evaluation_tests/test_golden_set.py
```

**Run specific golden tests**:

```bash
poetry run pytest -m "golden_test" evaluation_tests/test_golden_set.py \
  -k "golden_simple_formal_employment or golden_volunteer_student"
```

**Generate a baseline metrics report** (for regression tracking):

```bash
poetry run python evaluation_tests/generate_baseline_report.py
```

**Run golden transcript replay and check thresholds** (CI gating):

```bash
# Replay transcripts and collect metrics
poetry run python evaluation_tests/golden_transcript_runner.py \
  --transcripts-dir evaluation_tests/golden_transcripts \
  --output-dir evaluation_tests/golden_transcripts/output

# Validate against thresholds
poetry run python evaluation_tests/check_metrics_thresholds.py \
  --transcripts-dir evaluation_tests/golden_transcripts \
  --metrics-dir evaluation_tests/golden_transcripts/output
```

Test outputs are saved to `backend/evaluation_tests/test_output/` with timestamped folders for each run.

## Getting Started

Want to run Compass Connect on your own machine first? Follow the [self-hosting guide](docs/getting-started/README.md).

To work with this repository you should have a system with a bash compatible terminal (linux, macOS, cygwin) as most of the scripts are written for bash and will not work on windows cmd or powershell.

1. Fork the repository and clone it to your local environment.

2. Create a new branch for your changes.

3. Set up each individual subproject. e.g. if you are working on `backend/` follow instructions in `backend/README.md`

4. After making your changes, ensure the code is clean, properly formatted and passes all tests.

    You can use the provided script, `run-before-merge.sh`, for assistance. This script performs checking of the code formatting, linting, building, and testing on the subprojects of the repository. To run it, use the following command:
      
    ```bash
    ./run-before-merge.sh
    ```
      
    If you get any errors, fix them before proceeding. A common source of errors is not fully completing step `3` from above.

5. Commit them and push to your fork.

6. Use descriptive commit messages following [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

7. Open a pull request to our main branch.

Happy contributing! 🚀

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more information.

## Funders and Partners
<img src="frontend-new/public/logo_Google.org_Support_FullColor_cmyk%20coated_stacked.png" alt="Google.org Logo" width=200/>

This project is tested with BrowserStack.


