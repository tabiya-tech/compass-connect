"""
Tests of inject-config.py. Run from this directory: python3 -m unittest test_inject_config
"""
import importlib.util
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

    def test_replaces_a_text_override_with_escapes_verbatim(self):
        # GIVEN text overrides with a line break, a backslash and quotes are injected
        self.inject({"strings": {"es-ES": {"home.hero.body": "uno\ndos"}}})
        given_overrides = {"es-ES": {"home.hero.body": 'línea uno\nlínea dos \\ "tres"'}}

        # WHEN new ones replace them
        actual_content = self.inject({"strings": given_overrides})

        # THEN env.js holds them as serialized, with no raw line break inside the string
        actual_overrides = inject_config.extract_existing_frontend_json_value(actual_content, "FRONTEND_STRINGS_OVERRIDES")
        self.assertEqual(actual_overrides, given_overrides)
        # AND the key appears once
        self.assertEqual(actual_content.count("FRONTEND_STRINGS_OVERRIDES"), 1)

    def test_replaces_a_text_value_with_escapes_verbatim(self):
        # GIVEN a text value is injected
        self.inject({"branding": {"metaDescription": "first"}})

        # WHEN a value with a backslash and quotes replaces it
        actual_content = self.inject({"branding": {"metaDescription": 'C:\\path "quoted"'}})

        # THEN env.js holds it as serialized
        self.assertIn('FRONTEND_META_DESCRIPTION: btoa("C:\\\\path \\"quoted\\""),', actual_content)

    def test_wraps_only_non_ascii_values_for_utf8(self):
        # WHEN an ASCII value and a non-ASCII value are injected
        actual_content = self.inject({"branding": {"appName": "Compass", "metaDescription": "descripción"}})

        # THEN only the non-ASCII value is encoded as UTF-8 first
        self.assertIn('GLOBAL_PRODUCT_NAME: btoa("Compass"),', actual_content)
        self.assertIn('FRONTEND_META_DESCRIPTION: btoa(unescape(encodeURIComponent("descripción"))),', actual_content)


if __name__ == "__main__":
    unittest.main()
