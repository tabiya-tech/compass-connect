# Interface Texts

Replace individual texts of the interface for your deployment, per language, without changing the shared
translation files. Texts you do not override keep their built-in translation.

| Setting | `.env` variable | Values | Default |
|---|---|---|---|
| `strings` | `FRONTEND_STRINGS_OVERRIDES` | `{ "<locale>": { "<key>": "<text>" } }` | `{}` (built-in texts) |

```bash
FRONTEND_STRINGS_OVERRIDES={"es-ES":{"home.hero.headline1":"Descubramos","home.hero.body":"Conversa con {{appName}} y obtén tu informe de habilidades."}}
```

The same in a config file (see [Applying Changes](applying-changes.md#without-docker-local-development)):

```json
"strings": {
  "es-ES": {
    "home.hero.headline1": "Descubramos",
    "home.hero.body": "Conversa con {{appName}} y obtén tu informe de habilidades."
  }
}
```

## Finding a Key

1. Open `frontend-new/src/i18n/locales/<locale>/translation.json`, for example `es-ES`.
2. Search it for the text you see on the page.
3. Join the names that lead to it with dots: `"headline1"` inside `"hero"` inside `"home"` is `home.hero.headline1`.

## Rules

- **Override every language you offer.** An override applies to one locale only, and the locale must be one of the
  supported ones (for example `es-ES`, `en-US`). `en-GB` and `en-US` are separate: offer both, override both. A text
  for `es-ES` also applies when the browser asks for plain `es`.
- **Placeholders are filled in.** `{{appName}}` and `{{country}}` work as in the built-in texts (they come from
  [`branding.appName` and `branding.country`](branding.md#name-and-country)).
- **Typos do not break the page.** Overrides that name no existing text, or are not text, are ignored with a warning
  in the browser console.

## Limits

- **Only the interface.** What the AI says in the conversation is not changed.
- **Overrides do not follow upgrades.** An override replaces the whole text, so when a later version rewords the
  built-in text, your deployment keeps its own wording until you update it.

## Texts That Mention Modules

[Disabling a module](modules.md#disabling-modules) does not change texts that talk about it. Review these:

| Key | Mentions |
|---|---|
| `home.hero.body` | the journey through all modules |
| `home.footer.collaboration` | the default partners |

See the [skills-only example](modules.md#example-a-skills-only-deployment) for overrides of both.

To add a language or change the shared translations, see [Languages](languages.md).
