# Modules

All modules are enabled default, you can hide the ones your deployment does not use.

| Setting | `.env` variable | Values | Default |
|---|---|---|---|
| `modules.disabled` | `FRONTEND_DISABLED_MODULES` | list of module ids | `[]` (all modules on) |
| `modules.hideProgramSkills` | `FRONTEND_HIDE_PROGRAM_SKILLS` | `true` / `false` | `false` |
| `cv.enabled` | `GLOBAL_ENABLE_CV_UPLOAD` | `true` / `false` | `false` |
| `faq.tutorialVideoUrl` | `FRONTEND_FAQ_TUTORIAL_VIDEO_URL` | URL | no video |

## Disabling Modules

```bash
FRONTEND_DISABLED_MODULES=["career_explorer","job_matching"]
```

| Id | Module |
|---|---|
| `skills_discovery` | Build your profile (the skills conversation) |
| `career_explorer` | Career Explorer |
| `job_readiness` | Career Readiness learning modules |
| `knowledge_hub` | Knowledge Hub (career pathways) |
| `job_matching` | Job Matching |
| `faq` | Help (the FAQ page, with the tutorial video) |

A disabled module is hidden everywhere in the frontend:

- Its pages are removed: a direct link shows "not found".
- The links to it are removed: the home page cards, the navigation bar, the help button of the sign-in pages and the
  "Continue with ..." suggestion at the end of another module.
- A hand-off link whose action lands in a disabled module takes the user to the home page.

Keep in mind:

- **Texts still mention it.** Hiding a module does not change texts that talk about it, such as the home page
  introduction. Change them with [text overrides](texts.md#texts-that-mention-modules).
- **The backend is unchanged.** Only the frontend hides the module; its backend endpoints stay available.
- **Hiding `faq` removes all in-app help**, also before users sign in.
- **Unknown ids are ignored** with a warning in the browser console.

## Other Switches

- **Programme skills.** `FRONTEND_HIDE_PROGRAM_SKILLS=true` hides the skills of the user's training programme (the
  "TEVET programme skills" section) on the home page, in the conversation sidebar and on the profile. Use it when the
  deployment does not work with training programmes.
- **CV upload.** `GLOBAL_ENABLE_CV_UPLOAD=true` shows the CV upload and registers the CV APIs in the backend, which
  then also needs a storage bucket for the CVs (`BACKEND_CV_STORAGE_BUCKET`). When it is `false`, all CV UI is hidden.
- **Tutorial video.** `FRONTEND_FAQ_TUTORIAL_VIDEO_URL` is the video embedded in the Help page.

## Example: a Skills-Only Deployment

A deployment that offers only the skills conversation and its report, in Spanish, with its own partners:

```bash
FRONTEND_DISABLED_MODULES=["career_explorer","job_readiness","knowledge_hub","job_matching"]
FRONTEND_HIDE_PROGRAM_SKILLS=true
FRONTEND_DEFAULT_LOCALE=es-ES
FRONTEND_SUPPORTED_LOCALES=["es-ES"]
BACKEND_LANGUAGE_CONFIG={"default_locale":"es-ES","available_locales":[{"locale":"es-ES","date_format":"DD/MM/YYYY"}]}
GLOBAL_COUNTRY_NAME=Your Country
FRONTEND_PARTNER_LOGOS=[{"src":"https://www.example.org/logo.svg","alt":"Example Organization","height":40}]
FRONTEND_LOCALE_TEXT_OVERRIDES={"es-ES":{"home.hero.body":"Conversa con {{appName}} y descubre las habilidades que has ganado en tu trabajo, tus estudios y tu vida diaria. Al final obtendrás un informe de habilidades para compartir.","home.footer.collaboration":"{{appName}} es una herramienta gratuita de orientación profesional ofrecida por Example Organization en {{country}}."}}
```

- `home.hero.body` and `home.footer.collaboration` are the texts that mention the other modules and the default
  partners. Override them in every language the deployment offers (`FRONTEND_SUPPORTED_LOCALES`).
- Add `faq` to the disabled modules too if the partner provides its own help.

Apply the changes as described in [Applying Changes](applying-changes.md).
