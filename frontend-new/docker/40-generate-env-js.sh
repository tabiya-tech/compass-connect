#!/bin/sh
# Generates /usr/share/nginx/html/data/env.js from the container's environment variables, the same file that
# iac/frontend/prepare_frontend.py generates for the cloud deployment. Every value is base64 encoded (UTF-8),
# as the frontend expects (see src/envService.ts). Only variables that are set are written.
set -eu

OUT=/usr/share/nginx/html/data/env.js

KEYS="
FIREBASE_API_KEY
FIREBASE_AUTH_DOMAIN
BACKEND_URL
TARGET_ENVIRONMENT_NAME
FRONTEND_ENABLE_SENTRY
FRONTEND_SENTRY_DSN
FRONTEND_SENTRY_CONFIG
FRONTEND_ENABLE_METRICS
FRONTEND_METRICS_CONFIG
SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY
SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY_ID
FRONTEND_SENSITIVE_DATA_FIELDS
FRONTEND_LOGIN_CODE
GLOBAL_DISABLE_LOGIN_CODE
FRONTEND_REGISTRATION_CODE
GLOBAL_DISABLE_REGISTRATION_CODE
FRONTEND_DISABLE_REGISTRATION
GLOBAL_ENABLE_CV_UPLOAD
FRONTEND_ENABLE_NEW_SESSION
FRONTEND_HIDE_PROGRAM_SKILLS
FRONTEND_DISABLE_SOCIAL_AUTH
FRONTEND_FEATURES
FRONTEND_SUPPORTED_LOCALES
FRONTEND_DEFAULT_LOCALE
GLOBAL_PRODUCT_NAME
GLOBAL_COUNTRY_NAME
FRONTEND_BROWSER_TAB_TITLE
FRONTEND_META_DESCRIPTION
FRONTEND_SEO
FRONTEND_LOGO_URL
FRONTEND_PARTNER_LOGOS
FRONTEND_DARK_LOGO_URL
FRONTEND_FAVICON_URL
FRONTEND_APP_ICON_URL
FRONTEND_CHAT_AVATAR_URL
FRONTEND_THEME_CSS_VARIABLES
FRONTEND_SKILLS_REPORT_OUTPUT_CONFIG
FRONTEND_GTM_CONTAINER_ID
FRONTEND_GTM_ENABLED
FRONTEND_FAQ_TUTORIAL_VIDEO_URL
FRONTEND_ILLUSTRATIONS
"
REQUIRED="FIREBASE_API_KEY FIREBASE_AUTH_DOMAIN BACKEND_URL TARGET_ENVIRONMENT_NAME SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY_ID FRONTEND_SUPPORTED_LOCALES FRONTEND_DEFAULT_LOCALE"

missing=""
for key in $REQUIRED; do
    eval "value=\${$key:-}"
    [ -n "$value" ] || missing="$missing $key"
done
if [ -n "$missing" ]; then
    echo "ERROR: required frontend settings are missing or empty:$missing" >&2
    exit 1
fi

{
    echo "window.tabiyaConfig = {"
    for key in $KEYS; do
        # skip variables that are not set at all (set-but-empty ones are written as an empty value)
        eval "is_set=\${$key+x}"
        [ -n "$is_set" ] || continue
        eval "value=\${$key}"
        encoded=$(printf '%s' "$value" | base64 | tr -d '\n')
        echo "    \"$key\": \"$encoded\","
    done
    echo "};"
} > "$OUT"

echo "Generated $OUT"

# ---- index.html placeholders (same substitution as _patch_index_html in iac/frontend/prepare_frontend.py,
# but with defaults, so that a raw %%PLACEHOLDER%% is never shown) ----
INDEX=/usr/share/nginx/html/index.html
TEMPLATE=/usr/share/nginx/html/index.template.html

# escape for HTML attributes/text, then for the sed replacement
esc() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g' -e 's/[\/|&]/\\&/g'; }

title="${FRONTEND_BROWSER_TAB_TITLE:-${GLOBAL_PRODUCT_NAME:-Compass}}"
description="${FRONTEND_META_DESCRIPTION:-}"
seo="${FRONTEND_SEO:-}"
seo_name=$title; seo_url="${FRONTEND_URL:-}"; seo_image=""; seo_description=$description
if [ -n "$seo" ]; then
    seo_name=$(printf '%s' "$seo" | jq -r '.name // empty' 2>/dev/null || true); seo_name=${seo_name:-$title}
    seo_url=$(printf '%s' "$seo" | jq -r '.url // empty' 2>/dev/null || true); seo_url=${seo_url:-${FRONTEND_URL:-}}
    seo_image=$(printf '%s' "$seo" | jq -r '.image // empty' 2>/dev/null || true)
    seo_description=$(printf '%s' "$seo" | jq -r '.description // empty' 2>/dev/null || true); seo_description=${seo_description:-$description}
fi

sed -e "s|%%FRONTEND_BROWSER_TAB_TITLE%%|$(esc "$title")|g" \
    -e "s|%%FRONTEND_META_DESCRIPTION%%|$(esc "$description")|g" \
    -e "s|%%FRONTEND_SEO_NAME%%|$(esc "$seo_name")|g" \
    -e "s|%%FRONTEND_SEO_URL%%|$(esc "$seo_url")|g" \
    -e "s|%%FRONTEND_SEO_IMAGE%%|$(esc "$seo_image")|g" \
    -e "s|%%FRONTEND_SEO_DESCRIPTION%%|$(esc "$seo_description")|g" \
    "$TEMPLATE" > "$INDEX"
echo "Patched $INDEX"
