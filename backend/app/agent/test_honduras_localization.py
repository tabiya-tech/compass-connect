"""
Tests that Honduras is a supported country and that the agents' prompts get Honduras-specific context
(currency, job market, local terms) instead of the generic fallback.
"""
import pytest

from app.agent.preference_elicitation_agent.user_context_extractor import UserContextExtractor
from app.agent.preference_elicitation_agent.vignette_personalizer import VignettePersonalizer
from app.agent.recommender_advisor_agent.labor_market_contexts import HONDURAN_LABOR_MARKET_CONTEXT
from app.agent.recommender_advisor_agent.prompts import build_context_block
from app.countries import Country, get_country_from_string, get_country_glossary


class TestHondurasCountry:
    """Tests for Honduras in the Country enum."""

    @pytest.mark.parametrize("given_value", ["Honduras", "honduras", "HONDURAS"])
    def test_honduras_is_resolved_from_the_env_value(self, given_value: str):
        """DEFAULT_COUNTRY_OF_USER=Honduras resolves to Country.HONDURAS, not Unspecified."""
        # GIVEN the configured country value
        # WHEN it is resolved
        actual_country = get_country_from_string(given_value)

        # THEN it is Honduras
        assert actual_country == Country.HONDURAS

    def test_honduras_has_a_glossary(self):
        """Honduras has a glossary of local job terms."""
        # WHEN the glossary is requested
        actual_glossary = get_country_glossary(Country.HONDURAS)

        # THEN it contains local job terms
        assert "Pulpería" in actual_glossary
        assert "Maquila" in actual_glossary


class TestHondurasPromptContext:
    """Tests that each prompt builder returns Honduras-specific context."""

    def test_vignette_personalizer_uses_lempiras(self):
        """The job scenarios are written with lempiras and the Honduran job market."""
        # WHEN the country context for the job scenarios is built for Honduras
        actual_context = VignettePersonalizer._build_country_context(Country.HONDURAS)

        # THEN it names the lempira as the currency and rules out pesos
        assert "lempira (HNL)" in actual_context
        assert "never pesos" in actual_context
        # AND it is not the generic fallback
        assert actual_context != VignettePersonalizer._build_country_context(Country.UNSPECIFIED)

    def test_user_context_extractor_recognizes_honduran_roles(self):
        """Honduran companies and informal roles are mapped to sectors."""
        # WHEN the country examples are built for Honduras
        actual_examples = UserContextExtractor._build_country_examples(Country.HONDURAS)

        # THEN they include Honduran roles
        assert "maquila" in actual_examples
        assert "pulpería" in actual_examples

    def test_recommender_context_block_includes_the_honduran_labor_market(self):
        """The recommender gets the Honduran labor market context and glossary."""
        # WHEN the recommender context block is built for a Honduran user
        actual_block = build_context_block(
            skills=[],
            preference_vector={},
            recommendations_summary="",
            conversation_history="",
            country_of_user=Country.HONDURAS,
        )

        # THEN it includes the Honduran labor market context
        assert HONDURAN_LABOR_MARKET_CONTEXT in actual_block
        # AND the Honduran glossary
        assert get_country_glossary(Country.HONDURAS) in actual_block

    def test_honduran_user_profile_covers_returned_migrants(self):
        """The Honduran user profile is not limited to youth and includes people who returned from abroad."""
        # GIVEN the Honduran labor market context
        # THEN it describes returned migrants and work done abroad
        assert "returned to Honduras" in HONDURAN_LABOR_MARKET_CONTEXT
        assert "Experience gained abroad counts" in HONDURAN_LABOR_MARKET_CONTEXT
        # AND it no longer describes the users as youth only
        assert "Most users are youth" not in HONDURAN_LABOR_MARKET_CONTEXT
        # AND it asks the model not to probe why they returned or advise on migrating
        assert "Do not ask why someone returned" in HONDURAN_LABOR_MARKET_CONTEXT
        assert "do not give advice about migrating" in HONDURAN_LABOR_MARKET_CONTEXT
        # AND the job scenarios and the context extraction mention it too
        assert "returned from the United States" in VignettePersonalizer._build_country_context(Country.HONDURAS)
        assert "returned from the United States" in UserContextExtractor._build_country_examples(Country.HONDURAS)

    @pytest.mark.parametrize("given_assumption", [
        "deported",
        "Many are women",
        "stress",
        "safety concerns",
        "Most want jobs in customer service",
        "often basic",
    ])
    def test_honduran_user_profile_avoids_assumptions(self, given_assumption: str):
        """The profile does not assume users' gender, emotional state, skills, job wishes or migration reason."""
        # GIVEN a wording that would make the model assume something about every user
        # THEN it is not in the Honduran labor market context
        assert given_assumption not in HONDURAN_LABOR_MARKET_CONTEXT
