# Languages

Choose the languages of the interface and of the AI conversation.

| Setting | `.env` variable | What it is |
|---|---|---|
| `i18n.ui.defaultLocale` | `FRONTEND_DEFAULT_LOCALE` | language the interface loads in, for example `en-US` |
| `i18n.ui.supportedLocales` | `FRONTEND_SUPPORTED_LOCALES` | languages of the language switcher |
| `i18n.conversation` | `BACKEND_LANGUAGE_CONFIG` | languages of the AI conversation: `default_locale`, and `available_locales` with the `date_format` of each |

```bash
FRONTEND_DEFAULT_LOCALE=es-ES
FRONTEND_SUPPORTED_LOCALES=["es-ES","en-US"]
BACKEND_LANGUAGE_CONFIG={"default_locale":"es-ES","available_locales":[{"locale":"es-ES","date_format":"DD/MM/YYYY"},{"locale":"en-US","date_format":"MM/DD/YYYY"}]}
```

The interface is translated into `en-GB`, `en-US`, `es-ES`, `es-AR`, `sw-KE`, `ny-ZM` and `pt-MZ`. Date formats
combine `YYYY`, `YY`, `MM` and `DD` with `-`, `/` or `.`.

- **To change a few texts** for your deployment only, use [text overrides](texts.md).
- **To add a language or improve a translation** for everyone, see the [Language Guide](../../add-a-new-language.md).

Apply the changes as described in [Applying Changes](applying-changes.md).
