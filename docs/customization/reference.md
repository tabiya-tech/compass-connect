# Settings Reference

Every setting, its environment variable and its page. With Docker, set the variable in `.env`, with JSON values
(lists and objects) on one line; see [Applying Changes](applying-changes.md).
[`config/default.json`](../../config/default.json) has the complete structure with example values.

| Setting in `config/default.json` | Variable in `.env` | Used by | Page |
|---|---|---|---|
| `branding.appName` | `GLOBAL_PRODUCT_NAME` | backend and frontend | [Branding](branding.md#name-and-country) |
| `branding.country` | `GLOBAL_COUNTRY_NAME` | frontend | [Branding](branding.md#name-and-country) |
| `branding.browserTabTitle` | `FRONTEND_BROWSER_TAB_TITLE` | frontend | [Branding](branding.md#name-and-country) |
| `branding.metaDescription` | `FRONTEND_META_DESCRIPTION` | frontend | [Branding](branding.md#seo) |
| `branding.seo` | `FRONTEND_SEO` | frontend | [Branding](branding.md#seo) |
| `branding.assets.logo` | `FRONTEND_LOGO_URL` | frontend | [Branding](branding.md#logos-and-icons) |
| `branding.assets.darkLogo` | `FRONTEND_DARK_LOGO_URL` | frontend | [Branding](branding.md#logos-and-icons) |
| `branding.assets.favicon` | `FRONTEND_FAVICON_URL` | frontend | [Branding](branding.md#logos-and-icons) |
| `branding.assets.appIcon` | `FRONTEND_APP_ICON_URL` | frontend | [Branding](branding.md#logos-and-icons) |
| `branding.assets.chatAvatar` | `FRONTEND_CHAT_AVATAR_URL` | frontend | [Branding](branding.md#logos-and-icons) |
| `branding.partnerLogos` | `FRONTEND_PARTNER_LOGOS` | frontend | [Branding](branding.md#logos-and-icons) |
| `branding.illustrations` | `FRONTEND_ILLUSTRATIONS` | frontend | [Branding](branding.md#illustrations) |
| `branding.theme` | `FRONTEND_THEME_CSS_VARIABLES` | frontend | [Branding](branding.md#colors-and-fonts) |
| `modules.disabled` | `FRONTEND_DISABLED_MODULES` | frontend | [Modules](modules.md) |
| `modules.hideProgramSkills` | `FRONTEND_HIDE_PROGRAM_SKILLS` | frontend | [Modules](modules.md#other-switches) |
| `cv.enabled` | `GLOBAL_ENABLE_CV_UPLOAD` | backend and frontend | [Modules](modules.md#other-switches) |
| `faq.tutorialVideoUrl` | `FRONTEND_FAQ_TUTORIAL_VIDEO_URL` | frontend | [Modules](modules.md#other-switches) |
| `strings` | `FRONTEND_STRINGS_OVERRIDES` | frontend | [Interface Texts](texts.md) |
| `i18n.ui.defaultLocale` | `FRONTEND_DEFAULT_LOCALE` | frontend | [Languages](languages.md) |
| `i18n.ui.supportedLocales` | `FRONTEND_SUPPORTED_LOCALES` | frontend | [Languages](languages.md) |
| `i18n.conversation` | `BACKEND_LANGUAGE_CONFIG` | backend | [Languages](languages.md) |
| `auth.disableLoginCode` | `GLOBAL_DISABLE_LOGIN_CODE` | frontend | [Sign-In](sign-in.md) |
| `auth.disableRegistrationCode` | `GLOBAL_DISABLE_REGISTRATION_CODE` | backend and frontend | [Sign-In](sign-in.md) |
| `auth.disableRegistration` | `FRONTEND_DISABLE_REGISTRATION` | frontend | [Sign-In](sign-in.md) |
| `auth.disableSocialAuth` | `FRONTEND_DISABLE_SOCIAL_AUTH` | frontend | [Sign-In](sign-in.md) |
| `sensitiveData.fields` | `FRONTEND_SENSITIVE_DATA_FIELDS` | frontend | [Sign-In](sign-in.md#data-collection-fields) |
| `skillsReport` | `FRONTEND_SKILLS_REPORT_OUTPUT_CONFIG` | frontend | [Skills Report](skills-report.md) |
| `analytics.enabled` | `FRONTEND_GTM_ENABLED` | frontend | [Analytics](analytics.md) |
| `analytics.gtmContainerId` | `FRONTEND_GTM_CONTAINER_ID` | frontend | [Analytics](analytics.md) |

The other `analytics` settings (the GA4 and GTM account ids) are used by the [analytics setup script](analytics.md),
not by the running application.
