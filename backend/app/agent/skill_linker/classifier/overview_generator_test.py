from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.agent_types import LLMStats
from app.agent.experience.timeline import Timeline
from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.classifier.overview_generator import (
    ExperienceOverviewGenerator,
    ExperienceOverviewResponse,
    ExperienceOverviewResult,
)
from app.countries import Country
from app.i18n.translation_service import get_i18n_manager
from app.i18n.types import Locale


class TestGetPrompt:
    def test_includes_all_experience_metadata_and_qa(self):
        # GIVEN all pre-linking experience information
        prompt = ExperienceOverviewGenerator.get_prompt(
            experience_title="Shop Assistant",
            company_name="Uncle's Market",
            work_type=WorkType.UNSEEN_UNPAID,
            location="Cape Town, South Africa",
            timeline=Timeline(start="01-2023", end="06-2024"),
            responsibilities=["Serve customers", "Restock shelves"],
            questions_and_answers=[
                ("What kind of shop is it?", "A neighborhood grocery shop selling fresh produce."),
                ("Did you handle cash?", "Yes, I operated the till."),
            ],
        )

        # THEN every piece of context is formatted in the prompt
        assert "Experience Title: 'Shop Assistant'" in prompt
        assert "Company/Receiver of work: 'Uncle's Market'" in prompt
        assert "Work Type: 'Volunteer/Unpaid'" in prompt
        assert "Location: 'Cape Town, South Africa'" in prompt
        assert "Timeline: '01-2023 - 06-2024'" in prompt
        assert "Responsibilities: 'Serve customers, Restock shelves'" in prompt
        assert "Question: 'What kind of shop is it?'" in prompt
        assert "Answer: 'A neighborhood grocery shop selling fresh produce.'" in prompt
        assert "Question: 'Did you handle cash?'" in prompt
        assert "Answer: 'Yes, I operated the till.'" in prompt

    def test_handles_missing_optional_fields(self):
        # GIVEN only title and responsibilities
        prompt = ExperienceOverviewGenerator.get_prompt(
            experience_title="Baker",
            responsibilities=["Bake bread"],
        )

        # THEN optional fields fall back to N/A
        assert "Experience Title: 'Baker'" in prompt
        assert "Company/Receiver of work: 'N/A'" in prompt
        assert "Work Type: 'N/A'" in prompt
        assert "Location: 'N/A'" in prompt
        assert "Timeline: 'N/A'" in prompt
        assert "Questions & Answers: N/A" in prompt


class TestGetSystemInstructions:
    def test_includes_country_glossary_when_country_specified(self):
        # GIVEN an active locale and a specified country
        get_i18n_manager().set_locale(Locale.EN_US)
        instructions = ExperienceOverviewGenerator.get_system_instructions(country_of_interest=Country.SOUTH_AFRICA)

        # THEN the country context section is included
        assert "# Country Context" in instructions
        assert "SOUTH_AFRICA" in instructions

    def test_omits_country_glossary_when_unspecified(self):
        # GIVEN an active locale and an unspecified country
        get_i18n_manager().set_locale(Locale.EN_US)
        instructions = ExperienceOverviewGenerator.get_system_instructions(country_of_interest=Country.UNSPECIFIED)

        # THEN no country context section is included
        assert "# Country Context" not in instructions

    def test_instructs_not_to_repeat_responsibilities(self):
        # GIVEN an active locale
        get_i18n_manager().set_locale(Locale.EN_US)
        instructions = ExperienceOverviewGenerator.get_system_instructions(country_of_interest=Country.UNSPECIFIED)

        # THEN the instructions tell the LLM not to repeat individual responsibilities in the overview
        assert "do NOT list, enumerate, summarize, or repeat the individual responsibilities/tasks" in instructions


class TestExecute:
    @pytest.mark.asyncio
    async def test_returns_overview_professional_responsibilities_and_llm_stats(self):
        # GIVEN an LLM caller that returns a valid overview, professional responsibilities, and stats
        given_stats = [LLMStats(prompt_token_count=100, response_token_count=40, response_time_in_sec=0.5)]
        given_response = ExperienceOverviewResponse(
            reasoning="Synthesized from metadata and Q&A.",
            experience_overview="  Worked as a shop assistant at a neighborhood grocery store in Cape Town.  ",
            professional_responsibilities=["  Assist retail customers  ", "", "Restock grocery inventory"],
        )
        generator = ExperienceOverviewGenerator()
        generator._llm_caller.call_llm = AsyncMock(return_value=(given_response, given_stats))

        with patch.object(ExperienceOverviewGenerator, "get_llm", return_value=MagicMock()):
            # WHEN execute is called
            actual_result = await generator.execute(
                experience_title="Shop Assistant",
                company_name="Uncle's Market",
                work_type=WorkType.UNSEEN_UNPAID,
                location="Cape Town",
                timeline=Timeline(start="2023", end="2024"),
                country_of_interest=Country.SOUTH_AFRICA,
                responsibilities=["Serve customers"],
                questions_and_answers=[("What kind of shop?", "Grocery store")],
            )

        # THEN the stripped overview, formalized responsibilities, and llm stats are returned
        assert isinstance(actual_result, ExperienceOverviewResult)
        assert actual_result.overview == "Worked as a shop assistant at a neighborhood grocery store in Cape Town."
        assert actual_result.professional_responsibilities == ["Assist retail customers", "Restock grocery inventory"]
        assert actual_result.llm_stats == given_stats

    @pytest.mark.asyncio
    async def test_returns_empty_result_when_llm_returns_nothing(self):
        # GIVEN an LLM caller that returns None
        given_stats = [LLMStats(prompt_token_count=50, response_token_count=0, response_time_in_sec=0.2)]
        generator = ExperienceOverviewGenerator()
        generator._llm_caller.call_llm = AsyncMock(return_value=(None, given_stats))

        with patch.object(ExperienceOverviewGenerator, "get_llm", return_value=MagicMock()), \
             patch("app.agent.skill_linker.classifier.overview_generator.Retry.call_with_penalty",
                   new_callable=AsyncMock) as mock_retry:
            async def _run_once(*, callback, logger):
                return await callback(0, 1)

            mock_retry.side_effect = _run_once

            # WHEN execute is called
            actual_result = await generator.execute(
                experience_title="Baker",
                responsibilities=["Bake bread"],
            )

        # THEN an empty overview and empty responsibilities are returned along with the collected llm stats
        assert actual_result.overview == ""
        assert actual_result.professional_responsibilities == []
        assert actual_result.llm_stats == given_stats
