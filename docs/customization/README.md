# Compass Connect Customization Guide

A Compass Connect deployment can be customized without changing code: you set environment variables in
the `.env` file and run `docker compose up -d`. [Applying Changes](applying-changes.md) explains how, also without
Docker.

## What You Can Customize

| What | For example | Page |
|---|---|---|
| **Modules** | offer only the skills conversation; hide Job Matching or the Help page | [modules.md](modules.md) |
| **Interface texts** | reword the home page introduction; name your own partners | [texts.md](texts.md) |
| **Branding** | name, country, logos, partner logos, images, colors, fonts, SEO, legal documents | [branding.md](branding.md) |
| **Languages** | default language, languages of the switcher and of the conversation | [languages.md](languages.md) |
| **Sign-in and registration** | login-only access, no Google sign-in, the personal data form | [sign-in.md](sign-in.md) |
| **Skills report** | report logos, PDF and/or DOCX, which details it shows | [skills-report.md](skills-report.md) |
| **Analytics** | Google Analytics 4 through Google Tag Manager | [analytics.md](analytics.md) |

Every setting and its variable are listed in the [Settings Reference](reference.md).

Only these options can be customized. The core application logic, workflows and page layouts will require code changes to be customized.

## Beyond Configuration

To know more about adapting Compass Connect to a country's labour market — its taxonomy, sectors, curricula and job sources. See [Adapting to Your National Context](national-context.md).
