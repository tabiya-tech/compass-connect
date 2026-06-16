# Compass Connect Customisation Guide

This guide explains how to customise a Compass Connect deployment.
It documents which parts of the application can be changed, what the constraints are, and how to apply a configuration.

## Overview

Compass Connect is the base product. New deployments — such as Njila Zambia — are created by starting from Compass Connect and applying a configuration file that overrides the branding, colours, features, and content for that specific deployment.

No application code needs to change between deployments. Everything is controlled through a single JSON configuration file that is injected at deployment time.

## Creating a New Deployment

1. Copy `config/default.json` and give it a name that reflects your deployment (for example `config/njila.json`).
2. Update the values in your new file — branding, colours, features, and any other sections relevant to your deployment.
3. Apply the configuration locally by running:

```bash
cd config
python3 inject-config.py --config njila.json
```

4. Restart the frontend and backend to pick up the new values.

All available options are described in the sections below. Only the values you change need to be in your file — anything not specified falls back to the defaults in `default.json`.

## Configuration File

All supported customization options are defined in `config/default.json`.

This file is the **source of truth** for what can and cannot be customised.


## Configuration Structure

The configuration file is organized into the following sections:

- **branding** — Application name, logos, colours, illustrations, and SEO metadata
- **auth** — Authentication behaviour
- **cv** — CV feature availability
- **skillsReport** — Skills report branding, formats, and content
- **i18n** — Language and locale settings
- **analytics** — Google Analytics 4 and Google Tag Manager integration
- **faq** — Tutorial video URL
- **sensitiveData** — User data collection fields

Only options exposed in these sections are customizable. Core application logic, workflows, and page layouts are fixed.


## Branding Configuration

### Application Identity

- **appName**: Name displayed throughout the application
- **browserTabTitle**: Text shown in the browser tab

### SEO Metadata

- **metaDescription**: Search engine description
- **seo.name**: Site name for search results
- **seo.url**: Public application URL
- **seo.image**: Image used for social sharing
- **seo.description**: Detailed SEO description

### Assets

- **assets.logo**: Main logo (SVG recommended)
- **assets.darkLogo**: Dark variant of the logo, used on light backgrounds
- **assets.favicon**: Browser favicon
- **assets.appIcon**: Application icon
- **assets.chatAvatar**: Image shown as the AI assistant's avatar in the chat interface

Assets can be placed in the frontend `public` directory or hosted externally and referenced by URL.

### Partner Logos

- **partnerLogos**: List of logos shown in the application footer, each with a source URL, alt text, and optional height and width

### Illustrations

- **illustrations.loginHero**: Hero image on the login page
- **illustrations.loginFeature1**: First supporting feature image on the login page
- **illustrations.loginFeature2**: Second supporting feature image on the login page
- **illustrations.loginFeature3**: Third supporting feature image on the login page
- **illustrations.homeHero**: Hero image on the home page
- **illustrations.homeHeroIllustrationPosition**: Position of the home hero — `center` or `edge`
- **illustrations.careerReadinessHero**: Hero image on the career readiness page
- **illustrations.authShapesBackground**: Background shape image used on auth pages
- **illustrations.dashboardShapesBackground**: Background shape image used on the dashboard

### Theme Colours

Colours are defined using RGB values (for example: `"0 255 145"`). This format allows the application to apply transparency variants automatically.

The following colour roles can be customised. Each role has a main colour plus light, dark, and contrast-text variants:

- **Primary** — the main brand colour, used on primary action buttons and key interactive elements
- **Secondary** — used on section headers, cards, and supporting UI regions
- **Tertiary** — used for subtle backgrounds and lower-emphasis elements
- **Quaternary** — used for specific card backgrounds and highlight areas
- **Accent** — used on tag chips, inline highlights, and supporting accents
- **Neutral** — used on the navigation bar and neutral UI regions
- **Highlight** — used on skill tags and programme-related chip elements

Additional colours that can be customised:

- Navigation bar background and text colour
- Page background (main, light variant, dark variant, and contrast text)
- Primary, secondary, and accent text colours
- Heading and body font families

**Accessibility requirement:**

After updating colours, run Storybook locally and run the accessibility tests to ensure WCAG AA contrast compliance. Non-compliant colour combinations will fail accessibility checks.


## Feature Configuration

### CV Feature

- **cv.enabled**: Enable or disable CV functionality

When disabled, all CV-related UI elements are hidden and CV APIs are not registered.

### Authentication

- **auth.disableLoginCode**: Disable the login code requirement
- **auth.disableRegistrationCode**: Disable the registration code requirement
- **auth.disableRegistration**: Disable registration entirely, making the application login-only
- **auth.disableSocialAuth**: Hide social login options (for example Google sign-in)

These settings control how users authenticate and register in the application.


## Legal Documents

Each deployment has its own terms of use and privacy policy documents. The correct documents are served automatically based on the product name set in **branding.appName** (matched case-insensitively).

To add legal documents for a new deployment:

1. Add two Markdown files to `frontend-new/src/legal/documents/` following the naming convention:
   - `privacy-policy-{product-slug}.md`
   - `terms-of-use-{product-slug}.md`
2. Import both files and register them in `frontend-new/src/legal/legalDocumentLoader.ts`, adding an entry to `documentsByProductName` with the lowercased product name as the key and both `privacy` and `terms` documents as values.

If no entry is found for the product name, the application falls back to the default documents.


## Skills Report Configuration

The skills report supports branding, format, and content customisation.

### Report Logos

- **skillsReport.logos**: One or more logos displayed in generated reports

Separate sizing is supported for DOCX and PDF formats. This allows single-brand or co-branded reports.

### Download Formats

- **skillsReport.downloadFormats**: Control which formats are available — DOCX, PDF, or both

### Report Content

- **skillsReport.report.summary.show**: Show or hide the summary section
- **skillsReport.report.experienceDetails.title**: Show or hide the experience title
- **skillsReport.report.experienceDetails.companyName**: Show or hide the company name
- **skillsReport.report.experienceDetails.dateRange**: Show or hide the date range
- **skillsReport.report.experienceDetails.location**: Show or hide the location
- **skillsReport.report.experienceDetails.summary**: Show or hide the experience summary


## Localisation Configuration

Compass Connect supports multiple languages through configuration.

### User Interface Locales

- **i18n.ui.defaultLocale**: Default UI language
- **i18n.ui.supportedLocales**: List of available UI languages

### Conversation Locales

- **i18n.conversation.default_locale**: Default language for the AI conversation
- **i18n.conversation.available_locales**: Available conversation locales, each with a date format

For full translation setup, see the [Language Guide](../add-a-new-language.md).


## Sensitive Data Fields Configuration

The personal data collection form can be customised to collect different information per deployment.

- **sensitiveData.fields**: Configuration for each data collection field

This allows customisation of:

- Which fields are displayed (for example: name, email, gender, age, education)
- Whether each field is required or optional
- Field type (free text or a list of choices)
- Validation rules and error messages
- Labels and choice values per language

For the full schema and examples, see the [Sensitive Data Fields Configuration Guide](../frontend-new/sensitive-data-fields-config.md).


## Analytics Configuration

Compass Connect supports Google Analytics 4 (GA4) event tracking via Google Tag Manager (GTM).

- **analytics.enabled**: Enable or disable tracking in the frontend
- **analytics.gtmContainerId**: GTM container ID (for example: `GTM-XXXXXXX`)
- **analytics.ga4PropertyId**: GA4 property ID
- **analytics.ga4MeasurementId**: GA4 measurement ID (for example: `G-XXXXXXX`)

When enabled, the frontend automatically tracks user registration and login events.

For the full setup guide, see the [Analytics Setup Guide](ANALYTICS_SETUP.md).


## FAQ Configuration

The FAQ section includes a tutorial video that can be customised per deployment.

- **faq.tutorialVideoUrl**: URL of the tutorial video embedded in the FAQ page


## What Cannot Be Changed

The following are fixed across all deployments and cannot be altered through configuration:

- Page layouts and the structure of UI components
- Core AI conversation logic and skills discovery flow
- Navigation routes and URL structure
- Backend API endpoints and data models


## Applying Configuration Locally

The configuration is applied using the `inject-config.py` script.

Navigate to the `config` directory and run:

```bash
cd config
python3 inject-config.py --config your-config.json
```

This reads the configuration file and injects values into:

- Backend `.env` file
- Frontend `public/data/env.js` file

To apply only specific sections:

```bash
python3 inject-config.py --config your-config.json --namespaces branding auth
```


## Configuration Reference

Refer to [default.json](default.json) for the complete configuration structure and all supported options.

## Important Notes

- If a configuration value is missing or contains a typo, the application will fall back to its default value
- If changes do not appear after deployment, verify the injected environment variables
- Configuration keys must match the structure in **default.json** exactly
