# Sign-In and Registration

Choose how users sign in and what they tell you about themselves after registering.

## Sign-In

| Setting | `.env` variable | `true` means |
|---|---|---|
| `auth.disableLoginCode` | `GLOBAL_DISABLE_LOGIN_CODE` | no login code is asked |
| `auth.disableRegistrationCode` | `GLOBAL_DISABLE_REGISTRATION_CODE` | no registration code is asked (used by the backend and the frontend) |
| `auth.disableRegistration` | `FRONTEND_DISABLE_REGISTRATION` | login only: the register flow is hidden |
| `auth.disableSocialAuth` | `FRONTEND_DISABLE_SOCIAL_AUTH` | social login, such as Google, is hidden |

## Data Collection Fields

`sensitiveData.fields` (`FRONTEND_SENSITIVE_DATA_FIELDS`) sets the personal data form shown after registration. Each
field has its visibility, whether it is required, its type (free text or choices), its validation and its label in
each language.

See the [Sensitive Data Fields Configuration Guide](../../frontend-new/sensitive-data-fields-config.md) for the
schema and examples.

Apply the changes as described in [Applying Changes](applying-changes.md).
