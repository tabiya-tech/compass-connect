"""
Tests of inject-config.py. Run from this directory: python3 -m unittest test_inject_config
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("inject_config", Path(__file__).with_name("inject-config.py"))
inject_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inject_config)

ENV_JS = 'window.tabiyaConfig = {\n  GLOBAL_PRODUCT_NAME: btoa("Compass"),\n};\n'


class UpdateFrontendEnvTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env_js = Path(self.directory.name) / "env.js"
        self.env_js.write_text(ENV_JS)

    def tearDown(self):
        self.directory.cleanup()

    def inject(self, config):
        inject_config.update_frontend_env(config, self.env_js)
        return self.env_js.read_text()

    def inject_overrides(self, overrides):
        return self.inject({"i18n": {"ui": {"localeTextOverrides": overrides}}})

    def test_replaces_a_text_override_with_escapes_verbatim(self):
        # GIVEN text overrides with a line break, a backslash and quotes are injected
        self.inject_overrides({"es-ES": {"home.hero.body": "uno\ndos"}})
        given_overrides = {"es-ES": {"home.hero.body": 'línea uno\nlínea dos \\ "tres"'}}

        # WHEN new ones replace them
        actual_content = self.inject_overrides(given_overrides)

        # THEN env.js holds them as serialized, with no raw line break inside the string
        actual_overrides = inject_config.extract_existing_frontend_json_value(actual_content, "FRONTEND_LOCALE_TEXT_OVERRIDES")
        self.assertEqual(actual_overrides, given_overrides)
        # AND the key appears once
        self.assertEqual(actual_content.count("FRONTEND_LOCALE_TEXT_OVERRIDES"), 1)

    def test_replaces_a_text_value_with_escapes_verbatim(self):
        # GIVEN a text value is injected
        self.inject({"branding": {"metaDescription": "first"}})

        # WHEN a value with a backslash and quotes replaces it
        actual_content = self.inject({"branding": {"metaDescription": 'C:\\path "quoted"'}})

        # THEN env.js holds it as serialized
        self.assertIn('FRONTEND_META_DESCRIPTION: btoa("C:\\\\path \\"quoted\\""),', actual_content)

    def overrides_in(self, content):
        return inject_config.extract_existing_frontend_json_value(content, "FRONTEND_LOCALE_TEXT_OVERRIDES")

    def test_replaces_the_text_overrides_with_the_ones_supplied(self):
        # GIVEN text overrides for two locales are injected
        self.inject_overrides({"es-ES": {"home.hero.body": "texto"}, "en-US": {"common.ok": "Fine"}})

        # WHEN a config with one locale only is injected
        actual_content = self.inject_overrides({"en-US": {"common.ok": "Okay"}})

        # THEN the overrides of the removed locale are gone
        self.assertEqual(self.overrides_in(actual_content), {"en-US": {"common.ok": "Okay"}})

    def test_removes_every_text_override_when_they_are_empty(self):
        # GIVEN text overrides are injected
        self.inject_overrides({"es-ES": {"home.hero.body": "texto"}})

        # WHEN empty text overrides are injected
        actual_content = self.inject_overrides({})

        # THEN no override is left, so the bundled texts are used
        self.assertEqual(self.overrides_in(actual_content), {})

    def test_keeps_the_text_overrides_when_they_are_not_supplied(self):
        # GIVEN text overrides are injected
        given_overrides = {"es-ES": {"home.hero.body": "texto"}}
        self.inject_overrides(given_overrides)

        # WHEN a config with other i18n.ui settings but without text overrides is injected
        actual_content = self.inject({"i18n": {"ui": {"defaultLocale": "es-ES"}}})

        # THEN the overrides are kept
        self.assertEqual(self.overrides_in(actual_content), given_overrides)

    def test_still_merges_the_other_json_fields(self):
        # GIVEN a theme with two variables is injected
        self.inject({"branding": {"theme": {"brand-primary": "1 2 3", "brand-secondary": "4 5 6"}}})

        # WHEN a theme with one of them is injected
        actual_content = self.inject({"branding": {"theme": {"brand-primary": "7 8 9"}}})

        # THEN the other variable is kept
        actual_theme = inject_config.extract_existing_frontend_json_value(actual_content, "FRONTEND_THEME_CSS_VARIABLES")
        self.assertEqual(actual_theme, {"brand-primary": "7 8 9", "brand-secondary": "4 5 6"})

    def test_wraps_only_non_ascii_values_for_utf8(self):
        # WHEN an ASCII value and a non-ASCII value are injected
        actual_content = self.inject({"branding": {"appName": "Compass", "metaDescription": "descripción"}})

        # THEN only the non-ASCII value is encoded as UTF-8 first
        self.assertIn('GLOBAL_PRODUCT_NAME: btoa("Compass"),', actual_content)
        self.assertIn('FRONTEND_META_DESCRIPTION: btoa(unescape(encodeURIComponent("descripción"))),', actual_content)

    def test_replaces_a_text_override_containing_closing_parentheses(self):
        # GIVEN a text override with parentheses and a comma, as in the end of the btoa(...) expression, is injected
        self.inject_overrides({"en-US": {"home.hero.body": "Discover skills (from work (paid)), study and life."}})

        # WHEN a new one replaces it
        actual_content = self.inject_overrides({"en-US": {"home.hero.body": "Replaced"}})

        # THEN the whole old override is replaced, leaving none of its text behind
        self.assertEqual(self.overrides_in(actual_content), {"en-US": {"home.hero.body": "Replaced"}})
        self.assertNotIn("study and life", actual_content)

    def test_replaces_a_text_value_containing_closing_parentheses(self):
        # GIVEN a text value with parentheses and a comma is injected
        self.inject({"branding": {"metaDescription": "Skills (paid), study"}})

        # WHEN a new value replaces it
        actual_content = self.inject({"branding": {"metaDescription": "Replaced"}})

        # THEN the old value is replaced in place, not left beside a second key
        self.assertIn('FRONTEND_META_DESCRIPTION: btoa("Replaced"),', actual_content)
        self.assertNotIn("study", actual_content)
        self.assertEqual(actual_content.count("FRONTEND_META_DESCRIPTION"), 1)


_SPEECH = {
    "speechToText": {
        "enabled": True, "maxRecordingSeconds": 45, "maxAudioBytes": 1024,
        "locales": ["sw-KE", "en-US"],
    },
    "textToSpeech": {
        "enabled": False, "maxTextBytes": 3000,
        "locales": {"en-US": {"enabled": True, "voice": "Kore", "style": "warm"},
                    "en-GB": {"enabled": False, "voice": "Puck", "style": "calm"}},
    },
}


class SpeechConfigTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env_js = Path(self.directory.name) / "env.js"
        self.env_js.write_text(ENV_JS)
        self.backend_env = Path(self.directory.name) / ".env"
        self.backend_env.write_text("GLOBAL_PRODUCT_NAME=Compass\n")

    def tearDown(self):
        self.directory.cleanup()

    def frontend_speech_config(self):
        inject_config.update_frontend_env({"speech": _SPEECH}, self.env_js)
        return inject_config.extract_existing_frontend_json_value(self.env_js.read_text(), "FRONTEND_SPEECH_CONFIG")

    def test_gives_the_backend_each_feature_as_it_is_configured(self):
        # WHEN the speech config is injected into the backend .env
        inject_config.update_backend_env({"speech": _SPEECH}, self.backend_env)

        # THEN expect each feature to round-trip as JSON
        actual_lines = dict(line.split("=", 1) for line in self.backend_env.read_text().splitlines())
        self.assertEqual(json.loads(actual_lines["BACKEND_SPEECH_TO_TEXT_CONFIG"]), _SPEECH["speechToText"])
        self.assertEqual(json.loads(actual_lines["BACKEND_TEXT_TO_SPEECH_CONFIG"]), _SPEECH["textToSpeech"])

    def test_gives_the_frontend_only_the_switches_the_enabled_locales_and_its_limits(self):
        # WHEN the speech config is injected into the frontend env.js
        actual_config = self.frontend_speech_config()

        # THEN expect voice input, which is on, with its enabled locales, sorted, and its limit
        given_speech_to_text = _SPEECH["speechToText"]
        expected_speech_to_text_locales = sorted(given_speech_to_text["locales"])
        self.assertEqual(actual_config["speechToText"], {
            "enabled": given_speech_to_text["enabled"],
            "locales": expected_speech_to_text_locales,
            "maxRecordingSeconds": given_speech_to_text["maxRecordingSeconds"],
        })
        # AND read aloud, which is off, without locales even though one is enabled, and with its limit
        given_text_to_speech = _SPEECH["textToSpeech"]
        self.assertEqual(actual_config["textToSpeech"], {
            "enabled": given_text_to_speech["enabled"],
            "locales": [],
            "maxTextBytes": given_text_to_speech["maxTextBytes"],
        })

    def test_replaces_the_frontend_speech_config_instead_of_merging_it(self):
        # GIVEN a speech config with voice input on is injected
        self.frontend_speech_config()

        # WHEN a config without the speech-to-text section is injected
        inject_config.update_frontend_env({"speech": {"textToSpeech": _SPEECH["textToSpeech"]}}, self.env_js)

        # THEN expect voice input to be off, not kept from before
        actual_config = inject_config.extract_existing_frontend_json_value(self.env_js.read_text(), "FRONTEND_SPEECH_CONFIG")
        self.assertEqual(actual_config["speechToText"], {"enabled": False, "locales": []})
        # AND the key to appear once
        self.assertEqual(self.env_js.read_text().count("FRONTEND_SPEECH_CONFIG"), 1)

    def test_gives_the_frontend_only_the_enabled_locales_of_the_text_to_speech_settings(self):
        # GIVEN read aloud is on, with one enabled and one disabled locale
        given_text_to_speech = {**_SPEECH["textToSpeech"], "enabled": True}

        # WHEN the speech config is injected into the frontend env.js
        inject_config.update_frontend_env({"speech": {"textToSpeech": given_text_to_speech}}, self.env_js)

        # THEN expect only the enabled locale
        actual_config = inject_config.extract_existing_frontend_json_value(self.env_js.read_text(), "FRONTEND_SPEECH_CONFIG")
        expected_locales = sorted(
            locale for locale, settings in given_text_to_speech["locales"].items() if settings["enabled"])
        self.assertEqual(actual_config["textToSpeech"]["locales"], expected_locales)

    def test_leaves_the_frontend_speech_config_when_the_config_has_no_speech_section(self):
        # WHEN a config without a speech section is injected
        inject_config.update_frontend_env({"branding": {"appName": "Compass"}}, self.env_js)

        # THEN expect no speech config to be written, so both features stay off
        self.assertNotIn("FRONTEND_SPEECH_CONFIG", self.env_js.read_text())

    def test_skips_the_speech_config_when_its_namespace_is_not_selected(self):
        # WHEN the speech config is injected for the branding namespace only
        inject_config.update_frontend_env({"speech": _SPEECH, "branding": {"appName": "Compass"}}, self.env_js,
                                          namespaces=["branding"])

        # THEN expect no speech config to be written
        self.assertNotIn("FRONTEND_SPEECH_CONFIG", self.env_js.read_text())


if __name__ == "__main__":
    unittest.main()
