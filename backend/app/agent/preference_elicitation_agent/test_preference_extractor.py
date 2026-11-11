"""
Tests that the PreferenceExtractor writes its user-facing follow-up question in the user's language.
"""
from unittest.mock import patch, Mock

import pytest

from app.agent.preference_elicitation_agent import preference_extractor as preference_extractor_module
from app.agent.preference_elicitation_agent.preference_extractor import (
    PreferenceExtractor,
    _build_extraction_system_instructions,
)
from app.context_vars import user_language_ctx_var
from app.i18n.types import Locale


class TestBuildExtractionSystemInstructions:
    """Tests for the locale-aware extraction system instructions."""

    @pytest.mark.parametrize("given_locale", [Locale.ES_AR, Locale.ES_ES, Locale.SW_KE, Locale.PT_MZ, Locale.EN_US])
    def test_instructions_ask_for_the_follow_up_in_the_user_language(self, given_locale: Locale):
        """The follow-up question must be requested in the user's language."""
        # GIVEN a locale

        # WHEN the extraction system instructions are built for it
        actual_instructions = _build_extraction_system_instructions(given_locale)

        # THEN they ask for the suggested follow-up in that language
        assert f"you MUST write it ONLY in {given_locale.label()}" in actual_instructions
        # AND the language section is inside the system instructions block
        assert actual_instructions.index("<Language>") < actual_instructions.index("</System Instructions>")
        # AND the other fields are kept in English so downstream value matching keeps working
        assert "Keep every other field" in actual_instructions


class TestGetExtractionLLM:
    """Tests that the extraction LLM follows the per-request locale."""

    def test_llm_is_built_per_locale_and_memoized(self):
        """A new LLM is built when the locale changes, and reused for the same locale."""
        # GIVEN get_llm builds a distinct LLM on each call
        with patch.object(preference_extractor_module, "get_llm", side_effect=lambda **_: Mock()) as mock_get_llm:
            # AND an extractor constructed before any locale is known
            given_extractor = PreferenceExtractor()
            # THEN no LLM is built in the constructor
            mock_get_llm.assert_not_called()

            # WHEN the LLM is requested under es-AR twice
            token = user_language_ctx_var.set(Locale.ES_AR)
            try:
                actual_es_first = given_extractor._get_extraction_llm()
                actual_es_second = given_extractor._get_extraction_llm()
            finally:
                user_language_ctx_var.reset(token)

            # AND then under en-US
            token = user_language_ctx_var.set(Locale.EN_US)
            try:
                actual_en = given_extractor._get_extraction_llm()
            finally:
                user_language_ctx_var.reset(token)

        # THEN the same LLM is reused for the same locale
        assert actual_es_first is actual_es_second
        # AND a different LLM is used for another locale
        assert actual_en is not actual_es_first
        # AND each was built with instructions for its own language
        assert mock_get_llm.call_count == 2
        actual_es_instructions = mock_get_llm.call_args_list[0].kwargs["system_instructions"]
        actual_en_instructions = mock_get_llm.call_args_list[1].kwargs["system_instructions"]
        assert Locale.ES_AR.label() in actual_es_instructions
        assert Locale.EN_US.label() in actual_en_instructions
