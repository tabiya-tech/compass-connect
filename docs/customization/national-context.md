# Adapting to Your National Context

Beyond UI translations, Compass Connect can be adapted to fit your program's labor market realities and educational context. Each major module has configurable options and specific information requirements from the implementing team.

Unlike the rest of this guide, most of these adaptations are not settings in `.env`: they change the agents' prompts,
data and sources, and are planned with the implementing team. The ones that are settings link to their page.

## Build Your Profile (Skills Elicitation Agent)

The core Compass agent can be optimized for efficient, context-relevant skills elicitation:

- **Skills taxonomy** — Choose or build a localized taxonomy that best fits your labor market realities (e.g., the KESCO taxonomy in Kenya, national occupation standards in Zambia).
- **Employment types** — Configure and sequence the types of work/employment most relevant to ask your users.
- **Probing depth** — Adapt the extent to which the agent probes into tasks under a work experience.
- **Job preferences** — Turn on/off asking about job preferences.
- **CV upload & skills report** — Turn on/off CV upload and change skills report formatting options (see [CV Upload](modules.md#other-switches) and [Skills Report](skills-report.md)).

> **Information required**: National occupational taxonomy or standards to enable a localized skills taxonomy behind the agent.
>
> **Effort**: High — taxonomy localization requires dedicated research capacity.

## Career Readiness Learning Modules

The Job Readiness Learning Modules are designed for easy content and tutoring method adaptation:

- **Tutoring style** — Adapt system prompts to change tutoring styles (default is Scaffolded Socratic tutoring).
- **Module progression** — Turn on/off sequential module progression dependent on "passing".
- **Quizzes** — Turn on/off quiz-based end-of-module assessments.
- **Open support mode** — Turn on/off "Open support mode" post quiz completion.
- **Module content** — Change or add topics and lesson plans to the module list.

> **Information required**: Existing educational materials and curricula on practical or soft skills training for job readiness (e.g., in Zambia, TEVETA's Entrepreneurship course curriculum was used as content for one module).
>
> **Effort**: Low — module content is easily inserted once material is available.

## Career Explorer

The Career Explorer is optimized for adapting sectoral background content and what to spotlight:

- **Sectors** — Remove or change the sectors a user can explore, for more or less specialized guidance.
- **Priority sectors** — Choose which national priority sectors the agent nudges users to explore.
- **Sectoral data** — Ground the agent's context in nationally sourced and vetted sectoral data, training pathways, and career options.
- **Question guardrails** — Guardrail the types of user questions the agent should attempt to answer.
- **General knowledge** — Turn on/off whether the LLM uses general knowledge to answer questions.

> **Information required**: Labor market background documents (key economic sectors, national priorities, job concentration trends); national labor force survey microdata and reports; program offerings (training institutions and pathways available to users).
>
> **Effort**: Medium — may require dedicated research capacity depending on the quality of materials available.

## Job Matching

The Job Matching pipeline scrapes, classifies, and surfaces jobs to users:

- **Job sources** — Choose which job boards and aggregation sources to scrape from (e.g., gozambia.com in Zambia, or jobs provided directly by the implementing partner in Argentina).
- **Informal sources** — Explore sourcing jobs from non-traditional, informal sources such as social media channels (high development overhead).
- **Job detail columns** — Hide or unhide columns on job details visible to users.

> **Information required**: Preferred job boards and aggregation sources.
>
> **Effort**: Low.

## User Onboarding & Platform Access

- **Data collection fields** — Configure which user information fields the project wants to collect (see [Data Collection Fields](sign-in.md#data-collection-fields)).
- **Administrative integration** — Optionally integrate with a pre-existing administrative database of users.
- **FAQ and tutorials** — Provide non-technical onboarding guides and video tutorials accessible on the platform/FAQ (see [FAQ Video](modules.md#other-switches)).

> **Effort**: Low to medium — mostly configurable changes unless integration with an admin platform is required.

## Effort Summary

| Module | Information required from implementing team | Effort |
|---|---|---|
| User Onboarding & Access | User data fields to collect; optional pre-existing admin user database; onboarding guides and tutorial videos | Low–Medium |
| Build Your Profile | National occupational taxonomy or standards for localized skills taxonomy | High |
| Career Readiness Modules | Existing curricula on job-readiness and soft skills training | Low |
| Career Explorer | Labor market background docs, labor force surveys, program and institution listings | Medium |
| Job Matching | Preferred job boards and scraping sources | Low |
