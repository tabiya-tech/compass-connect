# Compass Customization Guide

This guide explains how-to white-label the Compass application using the supported configuration system.  
It documents which parts of the application can be customized, how configuration is applied, and how to validate changes.

## Overview

Compass supports white-label customization through a JSON-based configuration file.
This configuration controls branding, selected features, reports, and language settings.

Configuration values are injected into both the frontend and backend during deployment.

## Configuration File

All supported customization options are defined in `config/default.json`.

This file is the **source of truth** for what can and cannot be customized.

## Configuration Structure

The configuration file is organized into the following top-level namespaces:

- **branding**: Application name, logos, colors, and SEO metadata
- **auth**: Authentication behavior
- **cv**: CV feature availability
- **skillsReport**: Skills report branding, formats, and content
- **i18n**: Language and locale settings
- **analytics**: Google Analytics 4 and Google Tag Manager integration

Only options exposed in these namespaces are customizable. Core application logic, workflows, and layouts are fixed.

## Branding Configuration

### Application Identity

- **appName**: Name displayed throughout the application
- **browserTabTitle**: Text shown in the browser tab

![Application name](https://raw.githubusercontent.com/tabiya-tech/docs/main/.gitbook/assets/app-name.svg) ![Browser Tab title](https://raw.githubusercontent.com/tabiya-tech/docs/main/.gitbook/assets/browser-tab.svg)

*Figure 1: Application name and browser tab title*

### SEO Metadata

- **metaDescription**: Search engine description
- **seo.name**: Site name for search results
- **seo.url**: Public application URL
- **seo.image**: Image used for social sharing
- **seo.description**: Detailed SEO description

### Assets

- **assets.logo**: Main logo (SVG recommended)
- **assets.favicon**: Browser favicon
- **assets.appIcon**: Application icon

![Main logo](https://raw.githubusercontent.com/tabiya-tech/docs/main/.gitbook/assets/logo.svg) ![Favicon](https://raw.githubusercontent.com/tabiya-tech/docs/main/.gitbook/assets/favicon.svg) ![Application logo](https://raw.githubusercontent.com/tabiya-tech/docs/main/.gitbook/assets/app-logo.svg)

*Figure 2: Logo and icon assets*

Assets can be placed in the frontend `public` directory or hosted externally.

### Theme colors

colors are defined using RGB values (for example: `"0 255 145"`).

The following colors can be customized:

- Primary and secondary brand colors (including light, dark, and contrast text)
- Primary, secondary, and accent text colors

![Branding Colors](https://raw.githubusercontent.com/tabiya-tech/docs/main/.gitbook/assets/branding-colors.svg)

*Figure 3: Theme color application*

**Accessibility requirement:**  

After updating colors, run Storybook locally with the chosen configuration and **run the accessibility tests** to ensure WCAG AA contrast compliance. Non-compliant color combinations will fail accessibility checks.

## Feature Configuration

### CV Feature

- **cv.enabled**: Enable or disable CV functionality

When disabled, all CV-related UI elements are hidden and CV APIs are not registered.

![Feature CV](https://raw.githubusercontent.com/tabiya-tech/docs/main/.gitbook/assets/feature-cv.svg) 

*Figure 4: CV feature enabled*

### Authentication

- **auth.disableLoginCode**: Disable login code requirement
- **auth.disableRegistrationCode**: Disable registration code requirement

These settings control how users authenticate in the application.

![Login code enabled](https://raw.githubusercontent.com/tabiya-tech/docs/refs/heads/main/.gitbook/assets/login-code.svg) ![Registration code enabled](https://raw.githubusercontent.com/tabiya-tech/docs/main/.gitbook/assets/registration-code.svg)

*Figure 5: Login with code and registration with code enabled*

## Skills Report Configuration

The skills report supports branding, format, and content customization.

### Report Logos

- **skillsReport.logos**: One or more logos displayed in generated reports
- Separate sizing is supported for DOCX and PDF formats

This allows single-brand or co-branded reports.

### Download Formats

- **skillsReport.downloadFormats**: Control which formats are available (DOCX and/or PDF)

### Report Content

Partners can control which sections and fields appear in the report, including:

- Summary section
- Experience title
- Company name
- Date range
- Location

![Skills Report customization](https://raw.githubusercontent.com/tabiya-tech/docs/main/.gitbook/assets/skills-report.svg)

*Figure 6: Skills report customization*


## Localization Configuration

Compass supports multiple languages through configuration.

### User Interface Locales

- **i18n.ui.defaultLocale**: Default UI language
- **i18n.ui.supportedLocales**: Available UI languages

### Conversation Locales

- **i18n.conversation.default_locale**: Default conversation language
- **i18n.conversation.available_locales**: Locale-specific configuration, including date format

![Language Switcher](https://raw.githubusercontent.com/tabiya-tech/docs/main/.gitbook/assets/languages.svg)

*Figure 7: Language switcher interface*


For full translation setup, see the [Language Guide](../add-a-new-language.md).

## Sensitive Data Fields Configuration

The sensitive data form fields can be customized to collect different user information.

- **sensitiveData.fields**: Configuration for sensitive data collection fields

This allows customization of:
- Which fields are displayed (name, email, gender, age, etc.)
- Field types
- Validation rules and error messages
- Localized labels and values

![Sensitive Data Fields](https://raw.githubusercontent.com/tabiya-tech/docs/main/.gitbook/assets/sensitive-data-fields.svg)

*Figure 8: Sensitive data collection fields*


For the complete schema documentation and examples, see the [Sensitive Data Fields Configuration Guide](../frontend-new/sensitive-data-fields-config.md).

## Legal Documents Configuration

Partners can customise the Terms of Use and Privacy Policy documents shown on
`/terms-of-use` and `/privacy-policy`.

- **legal.documents.termsOfUse**: URL (site-relative or absolute) of the Terms of Use markdown document
- **legal.documents.privacyPolicy**: URL (site-relative or absolute) of the Privacy Policy markdown document

There are two ways to provide each document. Pick whichever is more convenient
per document — both keys are optional and can be mixed.

**Path A (recommended): replace the bundled markdown files in your fork.**
Replace the markdown files at `frontend-new/public/legal/terms-of-use.md` and
`frontend-new/public/legal/privacy-policy.md`. Each file may begin with a
YAML frontmatter block to set the page title:

```markdown
---
title: "Terms of Use"
---

# Terms of Use

Body content...
```

If the `title` frontmatter is omitted, the page title falls back to a sensible
default (`Terms of Use` for `termsOfUse`, `Privacy Policy` for `privacyPolicy`).

**Path B (alternative): host the document elsewhere.**
Set `legal.documents.termsOfUse` (and/or `legal.documents.privacyPolicy`) to an
absolute URL pointing to your own host. Make sure your host serves the markdown
with CORS that allows the deployment origin to fetch it.

> **Updates affect only new consents.** Updating a legal document changes what
> users see on the consent screen going forward. Users who previously accepted
> the previous version continue without re-prompts; there is no automated
> re-consent flow.

> **Per-locale documents (planned, not yet supported).** In a future release,
> each value will be extendable to `Record<Locale, string>` so partners can
> ship per-language documents (e.g.
> `"termsOfUse": { "en-US": "/legal/terms-en.md", "es-ES": "/legal/terms-es.md" }`).
> The current `string`-shape config will continue to work unchanged.

## Analytics Configuration

Compass supports Google Analytics 4 (GA4) event tracking via Google Tag Manager (GTM).

- **analytics.enabled**: Enable or disable GTM in the frontend
- **analytics.gtmContainerId**: GTM container ID (e.g., `GTM-XXXXXXX`)
- **analytics.ga4PropertyId**: GA4 property ID
- **analytics.ga4MeasurementId**: GA4 measurement ID (e.g., `G-XXXXXXX`)

When enabled, the frontend tracks `user_registered` and `user_login` events automatically.

The setup is automated via `backend/scripts/analytics/setup_analytics.py`, which creates the GA4 property, GTM container, tags,
triggers, and variables, then writes the generated IDs into the configuration file.

For the full setup guide including prerequisites and step-by-step instructions, see the [Analytics Setup Guide](ANALYTICS_SETUP.md).

## Applying Configuration Locally

The configuration is applied using the `inject-config.py` script.

Navigate to the `config` directory and run:

```bash
cd config
python3 inject-config.py
```

This script reads the configuration file and injects values into:

* Backend `.env` file
* Frontend `public/data/env.js` file

You can also apply only specific namespaces:

```bash
python3 inject-config.py --config default.json --namespaces branding auth
```

## Configuration Reference

Refer to [default.json](default.json) for the complete configuration structure and all supported options.

## Important Notes

- If a configuration value is missing or contains a typo, the application will fall back to its default value
- If changes do not appear after deployment, verify injected environment variables
- Configuration keys must match the structure in **default.json** exactly
