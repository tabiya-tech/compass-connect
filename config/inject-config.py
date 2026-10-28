import json
import argparse
import sys
import re
from pathlib import Path
from typing import Dict, Any, Optional, Iterable, Tuple


DEFAULT_BACKEND_ENV_PATH = '../backend/.env'
DEFAULT_FRONTEND_ENV_PATH = '../frontend-new/public/data/env.js'

BACKEND_ENV_MAP: Dict[str, str] = {
    'GLOBAL_PRODUCT_NAME': 'branding.appName',

    # i18n
    "BACKEND_LANGUAGE_CONFIG": "i18n.conversation",


    # Invitation Codes
    "GLOBAL_DISABLE_REGISTRATION_CODE": "auth.disableRegistrationCode",

    # CV Upload
    "GLOBAL_ENABLE_CV_UPLOAD": "cv.enabled",

    # Add more backend env vars here
}

FRONTEND_ENV_MAP: Dict[str, str] = {
    'GLOBAL_PRODUCT_NAME': 'branding.appName',
    'GLOBAL_COUNTRY_NAME': 'branding.country',
    'FRONTEND_BROWSER_TAB_TITLE': 'branding.browserTabTitle',
    'FRONTEND_META_DESCRIPTION': 'branding.metaDescription',
    'FRONTEND_LOGO_URL': 'branding.assets.logo',
    'FRONTEND_DARK_LOGO_URL': 'branding.assets.darkLogo',
    'FRONTEND_FAVICON_URL': 'branding.assets.favicon',
    'FRONTEND_APP_ICON_URL': 'branding.assets.appIcon',
    'FRONTEND_CHAT_AVATAR_URL': 'branding.assets.chatAvatar',
    'FRONTEND_PARTNER_LOGOS': 'branding.partnerLogos',
    'FRONTEND_FAQ_TUTORIAL_VIDEO_URL': 'faq.tutorialVideoUrl',
    'FRONTEND_ILLUSTRATIONS': 'branding.illustrations',
    'FRONTEND_THEME_CSS_VARIABLES': 'branding.theme',
    'FRONTEND_SEO': 'branding.seo',

    # Skills report
    "FRONTEND_SKILLS_REPORT_OUTPUT_CONFIG": "skillsReport",

    # Add more frontend env.js keys here

    # Invitation Codes
    "GLOBAL_DISABLE_LOGIN_CODE": "auth.disableLoginCode",
    "GLOBAL_DISABLE_REGISTRATION_CODE": "auth.disableRegistrationCode",
    "FRONTEND_DISABLE_REGISTRATION": "auth.disableRegistration",
    "FRONTEND_DISABLE_SOCIAL_AUTH": "auth.disableSocialAuth",

    # CV Upload
    "GLOBAL_ENABLE_CV_UPLOAD": "cv.enabled",

    # Modules
    "FRONTEND_DISABLED_MODULES": "modules.disabled",
    "FRONTEND_HIDE_PROGRAM_SKILLS": "modules.hideProgramSkills",

    # Text overrides
    "FRONTEND_STRINGS_OVERRIDES": "strings",

    # i18n
    "FRONTEND_DEFAULT_LOCALE": "i18n.ui.defaultLocale",
    "FRONTEND_SUPPORTED_LOCALES": "i18n.ui.supportedLocales",

    # Sensitive data Fields
    "FRONTEND_SENSITIVE_DATA_FIELDS": "sensitiveData.fields",

    # Analytics
    "FRONTEND_GTM_CONTAINER_ID": "analytics.gtmContainerId",
    "FRONTEND_GTM_ENABLED": "analytics.enabled",
}

FRONTEND_JSON_FIELDS = {
    'FRONTEND_THEME_CSS_VARIABLES',
    'FRONTEND_SEO',
    'FRONTEND_SKILLS_REPORT_OUTPUT_CONFIG',
    'FRONTEND_SUPPORTED_LOCALES',
    'FRONTEND_SENSITIVE_DATA_FIELDS',
    'FRONTEND_ILLUSTRATIONS',
    'FRONTEND_PARTNER_LOGOS',
    'FRONTEND_DISABLED_MODULES',
    'FRONTEND_STRINGS_OVERRIDES',
    # Add more JSON.stringify fields here
}

# JSON fields whose value in the config is complete: it replaces the one in env.js instead of being merged into it.
# The text overrides are the whole list of a deployment's texts, so removing one (or all, with {}) restores the
# bundled wording. Fields missing from the config keep their value either way.
FRONTEND_REPLACED_JSON_FIELDS = {
    'FRONTEND_STRINGS_OVERRIDES',
}


def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        print(f"Error: Config file not found at '{path}'")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}")
        sys.exit(1)


def get_by_dotted_path(obj: Any, dotted_path: str) -> Any:
    """Resolve a dotted path like 'branding.assets.logo' in a dict-like object."""
    current = obj
    for part in dotted_path.split('.'):
        if current is None:
            return None
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def coerce_env_value(value: Any) -> Optional[str]:
    """Coerce values for .env writing."""
    if value is None:
        return None
    if isinstance(value, bool):
        # Backend env conventions vary; keep simple true/false
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        v = value.strip()
        return v if v != '' else None

    # For dict/list: store JSON (ensure_ascii=False preserves unicode characters like accented letters)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def build_env_updates(config: Dict[str, Any], mapping: Dict[str, str], namespaces: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Build env var updates based on selected namespaces.

    If namespaces is provided, only mapping entries whose dotted-path starts with one of them are applied.
    """
    selected = set(namespaces) if namespaces else None

    updates: Dict[str, Any] = {}
    for env_key, dotted_path in mapping.items():
        top = dotted_path.split('.', 1)[0]
        if selected is not None and top not in selected:
            continue
        value = get_by_dotted_path(config, dotted_path)
        if value is None:
            continue
        updates[env_key] = value
    return updates


def upsert_env_lines(lines: list[str], key: str, value: str) -> list[str]:
    """Upsert a KEY=VALUE line into .env content preserving other lines."""
    new_line = f"{key}={value}\n"
    out: list[str] = []
    found = False

    for line in lines:
        if not found and line.lstrip().startswith(f"{key}="):
            out.append(new_line)
            found = True
        else:
            out.append(line)

    if not found:
        if out and not out[-1].endswith('\n'):
            out[-1] += '\n'
        out.append(new_line)

    return out


def update_backend_env(config: Dict[str, Any], env_path: Path, namespaces: Optional[Iterable[str]] = None):
    if not env_path.exists():
        print(f"Error: Backend .env file not found at '{env_path}'")
        sys.exit(1)

    updates_raw = build_env_updates(config, BACKEND_ENV_MAP, namespaces)

    if not updates_raw:
        return

    lines = env_path.read_text().splitlines(keepends=True)

    for key, raw_value in updates_raw.items():
        value = coerce_env_value(raw_value)
        if value is None:
            continue
        lines = upsert_env_lines(lines, key, value)

    env_path.write_text(''.join(lines))


# btoa() only takes Latin-1 text and the frontend decodes the base64 as UTF-8 (see getEnv in envService.ts), so values
# with other characters (e.g. "á") are wrapped to be encoded as UTF-8 first: btoa(unescape(encodeURIComponent(...))).
# ASCII values keep the plain btoa(...) form.
UTF8_WRAPPER_START = r'(?:unescape\(encodeURIComponent\(\s*)?'
UTF8_WRAPPER_END = r'(?:\)\)\s*)?'


def frontend_json_pattern(key: str, capture: bool = False) -> str:
    payload = '(.*?)' if capture else '.*?'
    return (rf'(?:"{re.escape(key)}"|{re.escape(key)}):\s*btoa\(\s*{UTF8_WRAPPER_START}'
            rf'JSON\.stringify\({payload}\)\s*{UTF8_WRAPPER_END}\),')


def frontend_scalar_pattern(key: str) -> str:
    return rf'(?:"{re.escape(key)}"|{re.escape(key)}):\s*btoa\([^)]+\){UTF8_WRAPPER_END},'


def btoa_expression(js_expression: str) -> str:
    if js_expression.isascii():
        return f'btoa({js_expression})'
    return f'btoa(unescape(encodeURIComponent({js_expression})))'


def extract_existing_frontend_json_value(content: str, key: str) -> Dict[str, Any]:
    """Extract the existing JSON.stringify payload for a key in env.js"""
    pattern = frontend_json_pattern(key, capture=True)
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(1).strip())
    except Exception:
        return {}


def insert_before_closing_brace(content: str, new_line: str) -> str:
    content = content.rstrip()
    if content.endswith('};'):
        return content[:-2] + new_line + '};\n'
    return content + new_line


def format_frontend_replacement(key: str, raw_value: Any, existing_content: str) -> Tuple[str, int]:
    """Return (replacement_string, regex_flags)."""
    if key in FRONTEND_JSON_FIELDS:
        # Merge dicts if possible so config can override but keep existing keys
        existing = extract_existing_frontend_json_value(existing_content, key)
        if key not in FRONTEND_REPLACED_JSON_FIELDS and isinstance(raw_value, dict) and isinstance(existing, dict):
            merged = {**existing, **raw_value}
        else:
            merged = raw_value

        formatted_json = json.dumps(merged, indent=2, ensure_ascii=False).replace('\n', '\n    ')
        stringified = f'\n    JSON.stringify({formatted_json})\n  '
        return f'{key}: {btoa_expression(stringified)},', re.DOTALL

    if isinstance(raw_value, bool):
        rendered = 'true' if raw_value else 'false'
    elif raw_value is None:
        rendered = ''
    else:
        rendered = str(raw_value)

    rendered = rendered.replace('\\', '\\\\').replace('"', '\\"')
    quoted = '"' + rendered + '"'
    return f'{key}: {btoa_expression(quoted)},', 0


def update_frontend_env(config: Dict[str, Any], env_js_path: Path, namespaces: Optional[Iterable[str]] = None):
    if not env_js_path.exists():
        print(f"Error: Frontend env.js file not found at '{env_js_path}'")
        sys.exit(1)

    content = env_js_path.read_text()

    updates = build_env_updates(config, FRONTEND_ENV_MAP, namespaces)
    if not updates:
        return

    # Clean up multiple consecutive empty lines
    content = re.sub(r'\n\n+', '\n', content)

    for key, raw_value in updates.items():
        replacement, flags = format_frontend_replacement(key, raw_value, content)

        pattern = frontend_json_pattern(key) if key in FRONTEND_JSON_FIELDS else frontend_scalar_pattern(key)

        if re.search(pattern, content, flags):
            # a function as replacement: re.sub would otherwise read the escapes of the serialized value (e.g. "\n")
            content = re.sub(pattern, lambda _match: replacement, content, count=1, flags=flags)
        else:
            content = insert_before_closing_brace(content, f'  {replacement}\n')

    env_js_path.write_text(content)


def parse_args(argv: Optional[list[str]] = None):
    parser = argparse.ArgumentParser(
        description='Inject namespaced config into backend .env and frontend env.js',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 inject-config.py --config default.json
  python3 inject-config.py --config default.json --namespaces branding auth
  python3 inject-config.py --config default.json --backend-env backend/.env --frontend-env frontend-new/public/data/env.js
        """
    )

    parser.add_argument('--config', required=True, metavar='CONFIG_FILE', help='Path to config JSON (e.g., default.json)')
    parser.add_argument('--backend-env', default=DEFAULT_BACKEND_ENV_PATH, help='Path to backend .env')
    parser.add_argument('--frontend-env', default=DEFAULT_FRONTEND_ENV_PATH, help='Path to frontend env.js')
    parser.add_argument('--namespaces', nargs='*', default=None,
                        help='Only apply these top-level namespaces (e.g., branding, cvUpload). Omit to apply all mapped keys.')

    return parser.parse_args(argv)


def main():
    args = parse_args()

    config_path = Path(args.config)
    config = read_json(config_path)

    update_backend_env(config, Path(args.backend_env), args.namespaces)
    update_frontend_env(config, Path(args.frontend_env), args.namespaces)

    print('Configuration injected successfully')


if __name__ == '__main__':
    main()
